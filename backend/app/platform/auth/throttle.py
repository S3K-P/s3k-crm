"""Per-address throttling for the unauthenticated authentication endpoints.

Sits in front of ``/auth/login`` and ``/auth/signup``: the two routes that
accept credentials from nobody in particular and are therefore the ones an
attacker can hammer without an account.

``/auth/refresh`` is deliberately **not** throttled. It requires an
unguessable rotating token, a stolen one is already detected and revoked by
reuse detection, and throttling it would let one attacker with a forged
address lock a legitimate user's session-refresh loop out of the product.
``/auth/change-password`` is authenticated, so the actor is known and the
audit trail — not a counter on an address — is the right control.
"""

from __future__ import annotations

import structlog
from fastapi import Request, status

from app.core.exceptions import AppError
from app.core.rate_limit import RateLimiter, client_address_for_limiting

logger = structlog.get_logger(__name__)

#: One bucket for both credential endpoints, so an attacker cannot double
#: their budget by alternating between signing up and signing in.
AUTH_BUCKET = "auth"


class TooManyAttemptsError(AppError):
    """The address has made too many credential attempts in the window."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_attempts"
    message = "Too many sign-in attempts from this network. Please try again shortly."


class AuthThrottle:
    """Counts credential attempts per client address.

    Says nothing about whether the account exists, the password was right, or
    how many attempts remain: the message is identical for every rejected
    caller, so the response cannot be used to enumerate accounts or to
    measure the limit precisely.
    """

    def __init__(self, request: Request) -> None:
        settings = request.app.state.settings
        self._limiter = RateLimiter(getattr(request.app.state, "redis", None))
        self._limit = settings.login_rate_limit_attempts
        self._window = settings.login_rate_limit_window_seconds
        self.address = client_address_for_limiting(
            request, trusted_proxy_hops=settings.trusted_proxy_hops
        )

    async def check(self) -> None:
        """Record this attempt and refuse it if the address is over budget.

        Raises:
            TooManyAttemptsError: 429, with ``Retry-After``.
        """
        verdict = await self._limiter.check(
            bucket=AUTH_BUCKET,
            identity=self.address,
            limit=self._limit,
            window_seconds=self._window,
        )
        if verdict.allowed:
            return

        logger.warning(
            "auth_rate_limited",
            address=self.address,
            used=verdict.used,
            limit=verdict.limit,
        )
        raise TooManyAttemptsError(
            details={"retry_after_seconds": verdict.retry_after}
        )

    async def clear(self) -> None:
        """Forget this address's attempts after a successful authentication.

        Without this, one person mistyping their password on a shared office
        address would spend the whole floor's budget for the window. A
        successful sign-in is the strongest available evidence that the
        traffic from this address is not an attack.
        """
        await self._limiter.reset(bucket=AUTH_BUCKET, identity=self.address)


__all__ = ["AUTH_BUCKET", "AuthThrottle", "TooManyAttemptsError"]
