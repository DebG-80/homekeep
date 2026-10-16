from __future__ import annotations

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.security.actor import ActorKind, Grant, HouseholdRole, StaffGroup
from app.security.local_issuer import LocalIssuer
from app.security.membership import resolve_actor
from app.security.tokens import SCOPE_MCP, AccessTokenVerifier, StaticJwks, VerifiedToken
from app.store import keys
from app.store.table import Table


def _member(
    table: Table, sub: str, household: str, *, role: str, grants: list[str], status: str = "ACTIVE"
) -> None:
    table.put(
        {
            "PK": keys.user_pk(sub),
            "SK": keys.user_household_sk(household),
            "household_id": household,
        }
    )
    table.put(
        {
            "PK": keys.household_pk(household),
            "SK": keys.member_sk(sub),
            "role": role,
            "grants": grants,
            "status": status,
            "version": 1,
        }
    )


def _token(sub: str, groups: frozenset[str] = frozenset()) -> VerifiedToken:
    return VerifiedToken(sub=sub, client_id="web", scopes=frozenset({SCOPE_MCP}), groups=groups)


def test_inv1_household_comes_only_from_membership_lookup(
    table: Table, issuer: LocalIssuer
) -> None:
    _member(table, "sub-owner", "hh-a", role="OWNER", grants=["view", "edit", "book", "updates"])
    _member(table, "sub-other", "hh-b", role="OWNER", grants=["view"])

    # A forged household claim in a validly signed token is ignored: only the lookup counts.
    forged = issuer.mint(
        "sub-owner",
        client_id="web",
        scopes=[SCOPE_MCP],
        extra_claims={"custom:household_id": "hh-b", "household_id": "hh-b"},
    )
    verified = AccessTokenVerifier(issuer.issuer, ["web"], StaticJwks(issuer.jwks)).verify(
        forged, SCOPE_MCP
    )
    actor = resolve_actor(table, verified)

    assert actor.kind is ActorKind.HOUSEHOLD
    assert actor.household_id == "hh-a"
    assert actor.role is HouseholdRole.OWNER
    assert actor.grants == {Grant.VIEW, Grant.EDIT, Grant.BOOK, Grant.UPDATES}

    # No membership and no staff group: no access at all.
    with pytest.raises(DomainError) as caught:
        resolve_actor(table, _token("sub-stranger"))
    assert caught.value.code is ErrorCode.AUTH_DENIED

    # Staff come from Cognito groups and get no household scope.
    staff = resolve_actor(table, _token("sub-tech", frozenset({"technician", "not-a-group"})))
    assert staff.kind is ActorKind.STAFF
    assert staff.household_id is None
    assert staff.groups == {StaffGroup.TECHNICIAN}

    # A subject linked to two households is ambiguous and denied, not guessed.
    _member(table, "sub-owner", "hh-c", role="OWNER", grants=["view"])
    with pytest.raises(DomainError) as caught:
        resolve_actor(table, _token("sub-owner"))
    assert caught.value.reason == "MULTIPLE_HOUSEHOLDS"


def test_fr20_revoked_member_denied_on_next_request(table: Table) -> None:
    _member(table, "sub-helper", "hh-a", role="HELPER", grants=["view", "book"])
    assert resolve_actor(table, _token("sub-helper")).household_id == "hh-a"

    # Revocation is a DynamoDB change; the same (still unexpired) token is denied next time.
    member = table.get(keys.household_pk("hh-a"), keys.member_sk("sub-helper"))
    assert member is not None
    table.put_versioned({**member, "status": "REVOKED", "version": 2}, expected_version=1)

    with pytest.raises(DomainError) as caught:
        resolve_actor(table, _token("sub-helper"))
    assert (caught.value.code, caught.value.reason) == (
        ErrorCode.AUTH_DENIED,
        "NO_ACTIVE_MEMBERSHIP",
    )


def test_g2_7_malformed_membership_denied(table: Table) -> None:
    _member(table, "sub-odd", "hh-a", role="SUPERUSER", grants=["view"])
    with pytest.raises(DomainError) as caught:
        resolve_actor(table, _token("sub-odd"))
    assert (caught.value.code, caught.value.reason) == (
        ErrorCode.AUTH_DENIED,
        "MALFORMED_MEMBERSHIP",
    )
