"""Data access for the auth module. The only layer here that builds queries."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform.auth.models import Session, User, UserProfile


class AuthRepository:
    """Queries over ``users``, ``user_profiles`` and ``sessions``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Users -------------------------------------------------------------

    async def get_user_by_email(self, email: str) -> User | None:
        """Case-insensitive lookup; addresses are stored lowercased."""
        result = await self._session.execute(
            select(User).where(User.email == email.strip().lower(), User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_users(self, user_ids: Sequence[uuid.UUID]) -> Sequence[User]:
        """Look up several users at once, with their profiles loaded.

        A directory read: the organizations module uses it to put a name and an
        address against each membership row. Profiles are eager-loaded because
        the caller always needs them, and lazy-loading them one at a time
        raises ``MissingGreenlet`` under asyncio.

        An empty request returns an empty sequence rather than issuing a query
        with an empty ``IN`` clause.
        """
        if not user_ids:
            return []
        result = await self._session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.id.in_(list(user_ids)), User.deleted_at.is_(None))
        )
        return result.scalars().all()

    async def add_user(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def add_profile(self, profile: UserProfile) -> UserProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

    # --- Sessions ----------------------------------------------------------

    async def get_session_by_token_hash(self, digest: str) -> Session | None:
        result = await self._session.execute(
            select(Session).where(Session.refresh_token_hash == digest)
        )
        return result.scalar_one_or_none()

    async def get_session(self, session_id: uuid.UUID) -> Session | None:
        result = await self._session.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def add_session(self, session: Session) -> Session:
        self._session.add(session)
        await self._session.flush()
        return session

    async def revoke_family(self, family_id: uuid.UUID, *, at: dt.datetime) -> int:
        """Revoke every live session in a lineage. Returns the number affected.

        Used both for logout and — critically — for refresh-token reuse
        detection, where a single replayed token invalidates the whole family.
        """
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Session)
                .where(Session.family_id == family_id, Session.revoked_at.is_(None))
                .values(revoked_at=at)
            ),
        )
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, at: dt.datetime) -> int:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Session)
                .where(Session.user_id == user_id, Session.revoked_at.is_(None))
                .values(revoked_at=at)
            ),
        )
        return int(result.rowcount or 0)

    async def mark_rotated(self, session_id: uuid.UUID, *, at: dt.datetime) -> None:
        await self._session.execute(
            update(Session).where(Session.id == session_id).values(rotated_at=at)
        )


__all__ = ["AuthRepository"]
