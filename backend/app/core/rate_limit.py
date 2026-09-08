"""Redis fixed-window rate limiting, and the trusted client address it keys on.

The account lockout in :mod:`app.platform.auth.service` stops somebody guessing
one password many times. It does nothing about the other shape of the attack —
one password tried against many accounts — because each account sees a single
failure and never trips. That is credential stuffing, and it is the common
case; this module is what makes it expensive.

**Two properties matter more than the counting.**

*Getting the address right.* ``X-Forwarded-For`` is appended to by each proxy,
so its **left-most** entry is whatever the original client claimed. Keying a
limit on that value hands every attacker an unlimited supply of identities and
makes the control decorative. The address is therefore counted from the
**right**, skipping exactly as many hops as we actually run
(:attr:`Settings.trusted_proxy_hops`), which is the only entry an attacker
cannot forge. ``app.core.request_context.client_address`` still reads the
left-most value, and correctly: it feeds audit records and logs, where the
client's own claim is the interesting datum and is never trusted.

*Failing open, deliberately.* If Redis is unreachable the limiter allows the
request and logs loudly. Failing closed would turn a cache outage into a total
authentication outage, and the durable control — per-account lockout, in
PostgreSQL, in the same transaction as the failed attempt — is unaffected by
Redis being down. This is the same call ``AiPromptService`` makes for spend
limits, reached here for a different and more carefully weighed reason.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from starlette.requests import Request

logger = structlog.get_logger(__name__)

#: Longest address string kept. An IPv6 address with a zone is comfortably
#: under this; anything longer is not an address and is discarded rather than
#: truncated into a key collision.
MAX_ADDRESS_LENGTH = 45

#: Key used when no address can be established at all. Every such request
#: shares one bucket, which is the safe direction: an attacker who could strip
#: their own address would land in the most contended bucket, not escape.
UNKNOWN_ADDRESS = "unknown"

FORWARDED_FOR_HEADER = "x-forwarded-for"


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    """The outcome of one check, including what to tell the caller to do."""

    allowed: bool
    #: Attempts recorded in the current window, including this one.
    used: int
    limit: int
    #: Seconds until the window resets. Surfaced as ``Retry-After``.
    retry_after: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def client_address_for_limiting(request: Request, *, trusted_proxy_hops: int) -> str:
    """The client address that cannot be forged from outside the proxy chain.

    With ``trusted_proxy_hops`` proxies in front of the application, the last
    ``trusted_proxy_hops`` entries of ``X-Forwarded-For`` were written by
    infrastructure we run and everything to their left was supplied by the
    client. The first entry to the left of ours is therefore the real peer.

    Falls back to the socket address whenever the header is absent, malformed,
    or shorter than the configured hop count — the last of which means the
    deployment is not behind as many proxies as it thinks, and the socket peer
    is then the honest answer rather than a client-supplied one.

    Args:
        request: the inbound request.
        trusted_proxy_hops: proxies between the internet and this process.
            ``0`` means the socket peer *is* the client and the header is
            ignored entirely.
    """
    peer = _normalise(request.client.host if request.client else None)

    if trusted_proxy_hops <= 0:
        return peer or UNKNOWN_ADDRESS

    raw = request.headers.get(FORWARDED_FOR_HEADER)
    if not raw:
        return peer or UNKNOWN_ADDRESS

    entries = [entry.strip() for entry in raw.split(",") if entry.strip()]
    # The right-most entry was written by the proxy nearest us. Skipping
    # `trusted_proxy_hops - 1` more lands on the address our outermost proxy
    # observed, which is the first value no client controls.
    index = len(entries) - trusted_proxy_hops
    if index < 0:
        # Fewer hops than configured: the chain is shorter than the deployment
        # claims. Trusting any entry here would trust a client-written one.
        logger.warning(
            "forwarded_for_shorter_than_expected",
            entries=len(entries),
            expected_hops=trusted_proxy_hops,
        )
        return peer or UNKNOWN_ADDRESS

    return _normalise(entries[index]) or peer or UNKNOWN_ADDRESS


def _normalise(value: str | None) -> str | None:
    """A canonical address string, or ``None`` if this is not an address.

    Parsed rather than pattern-matched so that ``1.2.3.4`` and ``1.2.3.04`` —
    and the many spellings of one IPv6 address — cannot occupy separate
    buckets and multiply an attacker's budget.
    """
    if not value:
        return None
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:  # [::1]:443
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # 1.2.3.4:443
        candidate = candidate.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))[:MAX_ADDRESS_LENGTH]
    except ValueError:
        return None


class RateLimiter:
    """Fixed-window counters in Redis.

    A fixed window rather than a sliding log: the log is more precise at the
    boundary and costs a sorted set per identity, and the imprecision here is
    that an attacker may get up to twice the limit across two adjacent
    windows. Against a control whose job is to make stuffing expensive rather
    than impossible, that factor of two does not change the economics, and the
    fixed window's single ``INCR`` does.
    """

    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis

    async def check(
        self, *, bucket: str, identity: str, limit: int, window_seconds: int
    ) -> RateLimitVerdict:
        """Record one attempt against ``identity`` and say whether to allow it.

        The counter is incremented before the verdict, so a rejected attempt
        still counts — an attacker cannot hold their budget steady by ignoring
        the rejections.
        """
        if self._redis is None:
            return RateLimitVerdict(True, used=0, limit=limit, retry_after=0)

        key = f"ratelimit:{bucket}:{identity}"
        try:
            used = int(await self._redis.incr(key))
            if used == 1:
                await self._redis.expire(key, window_seconds)
                retry_after = window_seconds
            else:
                ttl = int(await self._redis.ttl(key))
                # A key with no TTL means EXPIRE was lost between the INCR and
                # here; re-applying it is better than a counter that never
                # resets and locks the address out permanently.
                if ttl < 0:
                    await self._redis.expire(key, window_seconds)
                    ttl = window_seconds
                retry_after = ttl
        except Exception:
            # See the module docstring: the durable control is the account
            # lockout in PostgreSQL, and it is unaffected by this.
            logger.warning("rate_limit_unavailable", bucket=bucket, exc_info=True)
            return RateLimitVerdict(True, used=0, limit=limit, retry_after=0)

        return RateLimitVerdict(
            allowed=used <= limit, used=used, limit=limit, retry_after=retry_after
        )

    async def reset(self, *, bucket: str, identity: str) -> None:
        """Forget an identity's attempts.

        Called after a successful authentication so that one person mistyping
        a password on a shared address does not spend the whole office's
        budget for the window.
        """
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"ratelimit:{bucket}:{identity}")
        except Exception:
            logger.warning("rate_limit_reset_failed", bucket=bucket, exc_info=True)


__all__ = [
    "MAX_ADDRESS_LENGTH",
    "UNKNOWN_ADDRESS",
    "RateLimitVerdict",
    "RateLimiter",
    "client_address_for_limiting",
]
