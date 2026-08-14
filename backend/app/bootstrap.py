"""Provision the first organization and its administrator.

Run once against a freshly migrated database::

    uv run python -m app.bootstrap \
        --organization "Acme" --email admin@acme.example

The password is read from ``BOOTSTRAP_PASSWORD`` or prompted for; it is never
accepted as a command-line argument, because argv is visible to other processes
and lands in shell history.

Idempotent: an organization whose slug already exists, or a user whose address
is already registered, is reused rather than duplicated, so re-running after a
partial failure completes the job instead of erroring.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

import structlog

from app.core.config import Settings, load_settings_or_exit
from app.core.database import create_engine, create_session_factory
from app.platform.auth.repository import AuthRepository
from app.platform.auth.security import PasswordHasher
from app.platform.auth.service import AuthService
from app.platform.authorization.catalog import ADMIN_ROLE
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import OrganizationService, slugify
from app.products.crm.opportunities.service import OpportunityService

logger = structlog.get_logger(__name__)


def _read_password() -> str:
    """Take the password from the environment, or prompt for it."""
    from_env = os.environ.get("BOOTSTRAP_PASSWORD")
    if from_env:
        return from_env

    first = getpass.getpass("Administrator password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("FATAL: passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    return first


async def bootstrap(
    settings: Settings, *, organization_name: str, email: str, password: str
) -> None:
    """Create (or reuse) the organization, the admin user and the membership."""
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session, session.begin():
            organizations = OrganizationService(OrganizationRepository(session))
            authorization = AuthorizationService(AuthorizationRepository(session))
            auth = AuthService(
                repository=AuthRepository(session),
                organizations=OrganizationRepository(session),
                hasher=PasswordHasher(),
                issuer=None,  # type: ignore[arg-type]  # unused by register_user
                settings=settings,
            )

            slug = slugify(organization_name)
            existing_org = await OrganizationRepository(session).get_by_slug(slug)
            if existing_org is not None:
                organization = existing_org
                logger.info("bootstrap_organization_exists", slug=slug)
            else:
                organization = await organizations.create_organization(
                    name=organization_name
                )

            normalised = email.strip().lower()
            existing_user = await AuthRepository(session).get_user_by_email(normalised)
            if existing_user is not None:
                user = existing_user
                logger.info("bootstrap_user_exists", email=normalised)
            else:
                user = await auth.register_user(
                    email=normalised,
                    password=password,
                    first_name="Platform",
                    last_name="Administrator",
                )

            membership = await OrganizationRepository(session).get_membership(
                organization_id=organization.id, user_id=user.id
            )
            if membership is None:
                membership = await organizations.add_member(
                    organization_id=organization.id, user_id=user.id, is_default=True
                )

            admin_role = await authorization.get_system_role(ADMIN_ROLE)
            await authorization.assign_role_to_membership(
                membership_id=membership.id,
                role_id=admin_role.id,
                organization_id=organization.id,
            )

            # A pipeline must exist before any opportunity can be created.
            await OpportunityService(session).ensure_default_pipeline(
                organization.id, actor_id=user.id
            )

        print(
            f"Ready. Organization '{organization.name}' (slug: {organization.slug}) "
            f"with administrator {email}."
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the first organization and administrator."
    )
    parser.add_argument("--organization", required=True, help="Organization display name.")
    parser.add_argument("--email", required=True, help="Administrator email address.")
    args = parser.parse_args()

    settings = load_settings_or_exit()
    password = _read_password()

    asyncio.run(
        bootstrap(
            settings,
            organization_name=args.organization,
            email=args.email,
            password=password,
        )
    )


if __name__ == "__main__":
    main()
