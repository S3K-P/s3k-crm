"""Pure business rules that need no database: the lead state machine and RBAC
catalogue consistency."""

from __future__ import annotations

import pytest

from app.platform.authorization.catalog import (
    ADMIN_ROLE,
    MANAGER_ROLE,
    PERMISSION_ACTIONS,
    PERMISSION_MODULES,
    SYSTEM_ROLES,
    USER_ROLE,
    all_permission_codes,
    permissions_for_system_role,
)
from app.platform.authorization.models import PermissionAction
from app.products.crm.leads.models import LeadStatus
from app.products.crm.leads.service import CONVERTIBLE_FROM, LEAD_TRANSITIONS

# --- Permission catalogue ---------------------------------------------------


def test_the_catalogue_covers_every_module_and_action() -> None:
    assert len(all_permission_codes()) == len(PERMISSION_MODULES) * len(PERMISSION_ACTIONS)


def test_permission_codes_are_unique() -> None:
    codes = all_permission_codes()

    assert len(set(codes)) == len(codes)


def test_admin_holds_every_permission() -> None:
    """Expressed as a wildcard so a newly added module cannot omit Admin."""
    assert set(permissions_for_system_role(ADMIN_ROLE)) == set(all_permission_codes())


def test_manager_may_delete_but_user_may_not() -> None:
    manager = set(permissions_for_system_role(MANAGER_ROLE))
    user = set(permissions_for_system_role(USER_ROLE))

    assert "leads.DELETE" in manager
    assert "leads.DELETE" not in user


def test_user_may_read_create_and_edit_crm_records() -> None:
    user = set(permissions_for_system_role(USER_ROLE))

    assert {"leads.VIEW", "leads.CREATE", "leads.EDIT"} <= user


def test_no_system_role_grants_an_unknown_permission() -> None:
    catalogue = set(all_permission_codes())

    for name in SYSTEM_ROLES:
        assert set(permissions_for_system_role(name)) <= catalogue


def test_only_admin_holds_administrative_actions() -> None:
    for name in (MANAGER_ROLE, USER_ROLE):
        granted = set(permissions_for_system_role(name))
        assert not any(code.endswith(f".{PermissionAction.ADMIN.value}") for code in granted)


# --- Lead state machine -----------------------------------------------------


def test_every_status_has_a_transition_entry() -> None:
    """A status missing from the map would be silently unmovable."""
    assert set(LEAD_TRANSITIONS) == set(LeadStatus)


def test_converted_is_never_reachable_by_a_direct_transition() -> None:
    """Conversion must go through the workflow that creates the account."""
    for allowed in LEAD_TRANSITIONS.values():
        assert LeadStatus.CONVERTED not in allowed


def test_converted_is_terminal() -> None:
    assert LEAD_TRANSITIONS[LeadStatus.CONVERTED] == frozenset()


def test_a_lead_can_be_lost_from_any_open_status() -> None:
    open_statuses = set(LeadStatus) - {LeadStatus.CONVERTED, LeadStatus.LOST}

    for status in open_statuses:
        assert LeadStatus.LOST in LEAD_TRANSITIONS[status]


def test_a_lost_lead_can_be_reopened() -> None:
    assert LEAD_TRANSITIONS[LeadStatus.LOST]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LeadStatus.NEW, LeadStatus.CONTACTED),
        (LeadStatus.CONTACTED, LeadStatus.QUALIFIED),
        (LeadStatus.QUALIFIED, LeadStatus.PROPOSAL_SENT),
        (LeadStatus.PROPOSAL_SENT, LeadStatus.NEGOTIATION),
    ],
)
def test_the_happy_path_is_legal(current: LeadStatus, target: LeadStatus) -> None:
    assert target in LEAD_TRANSITIONS[current]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LeadStatus.NEW, LeadStatus.NEGOTIATION),
        (LeadStatus.NEW, LeadStatus.QUALIFIED),
        (LeadStatus.CONTACTED, LeadStatus.PROPOSAL_SENT),
    ],
)
def test_skipping_stages_is_illegal(current: LeadStatus, target: LeadStatus) -> None:
    assert target not in LEAD_TRANSITIONS[current]


def test_only_qualified_or_later_leads_are_convertible() -> None:
    assert LeadStatus.NEW not in CONVERTIBLE_FROM
    assert LeadStatus.CONTACTED not in CONVERTIBLE_FROM
    assert LeadStatus.QUALIFIED in CONVERTIBLE_FROM
