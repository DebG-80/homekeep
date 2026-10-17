"""The audited `hk-admin` CLI (plan P4-2): target guard, grants, revocation, faults."""

from __future__ import annotations

import io

from app.store import keys
from app.store.table import Table
from scripts import hk_admin, seed


def _run(table: Table, *argv: str, signed_out: list[str] | None = None) -> tuple[int, str]:
    out = io.StringIO()
    code = hk_admin.main(
        list(argv),
        out=out,
        table=table,
        sign_out=(signed_out.append if signed_out is not None else None),
    )
    return code, out.getvalue()


def _member(table: Table, household_id: str, display_name: str) -> dict:
    return next(
        m
        for m in table.query(keys.household_pk(household_id), keys.MEMBER_PREFIX)
        if m["display_name"] == display_name
    )


def test_cli_refuses_non_test_targets_and_dry_runs_without_yes(table: Table) -> None:
    seed.seed_local(table)
    before = table.client.scan(TableName=table.name)["Items"]
    code, out = _run(
        table, "--target", "aws", "--table-name", "homekeep-prod", "reset", "--household", "judge-1"
    )
    assert code == 2
    assert "refused" in out
    code, out = _run(
        table, "--target", "aws", "--table-name", "homekeep-test", "reset", "--household", "judge-1"
    )
    assert code == 1
    assert "Nothing written" in out
    assert table.client.scan(TableName=table.name)["Items"] == before


def test_cli_grants_and_revokes_through_the_domain_with_an_audit_trail(table: Table) -> None:
    seed.seed_local(table)
    code, _ = _run(
        table,
        "--target",
        "local",
        "grant",
        "--household",
        "qa-a",
        "--member",
        "hk-qa-a-viewer",
        "--grants",
        "view,edit",
    )
    assert code == 0
    assert _member(table, "qa-a", "hk-qa-a-viewer")["grants"] == ["view", "edit"]
    signed_out: list[str] = []
    code, _ = _run(
        table,
        "--target",
        "local",
        "revoke",
        "--household",
        "qa-a",
        "--member",
        "hk-qa-a-booker",
        signed_out=signed_out,
    )
    assert code == 0
    assert _member(table, "qa-a", "hk-qa-a-booker")["status"] == "REVOKED"
    assert signed_out == ["hk-qa-a-booker"]
    events = [
        e
        for e in table.query(keys.household_pk("qa-a"), keys.EVENT_PREFIX)
        if e["action"].startswith("MEMBER_")
    ]
    assert [(e["action"], e["actor_sub"], e["actor_role"]) for e in events] == [
        ("MEMBER_GRANTS_CHANGED", "admin:cli", "OPERATOR"),
        ("MEMBER_REVOKED", "admin:cli", "OPERATOR"),
    ]


def test_cli_sets_and_clears_faults_and_purges(table: Table) -> None:
    seed.seed_local(table)
    assert (
        _run(
            table,
            "--target",
            "local",
            "fault",
            "set",
            "--household",
            "judge-1",
            "--fault",
            "TIMEOUT_AFTER_SUCCESS",
            "--remaining",
            "2",
        )[0]
        == 0
    )
    fault = table.get(keys.PROVIDER_PK, keys.fault_sk("judge-1"))
    assert (fault["fault"], fault["remaining"]) == ("TIMEOUT_AFTER_SUCCESS", 2)
    assert (
        _run(
            table,
            "--target",
            "local",
            "fault",
            "set",
            "--household",
            "judge-1",
            "--fault",
            "NOT_A_FAULT",
        )[0]
        == 2
    )
    assert _run(table, "--target", "local", "fault", "clear", "--household", "judge-1")[0] == 0
    assert table.get(keys.PROVIDER_PK, keys.fault_sk("judge-1")) is None

    signed_out: list[str] = []
    code, out = _run(
        table, "--target", "local", "purge", "--household", "judge-3", signed_out=signed_out
    )
    assert code == 0
    assert table.query(keys.household_pk("judge-3")) == []
    assert signed_out == ["hk-judge-3"]
    assert "hk-judge-3" in out


def test_i10_a_failed_sign_out_is_reported_not_crashed(table: Table) -> None:
    seed.seed_local(table)
    out = io.StringIO()

    def failing(username: str) -> None:
        raise RuntimeError("cognito unavailable")

    code = hk_admin.main(
        ["--target", "local", "revoke", "--household", "qa-a", "--member", "hk-qa-a-booker"],
        out=out,
        table=table,
        sign_out=failing,
    )
    assert code == 1  # the revocation stands, but the operator must sign the user out by hand
    assert _member(table, "qa-a", "hk-qa-a-booker")["status"] == "REVOKED"
    assert "NOT signed out: hk-qa-a-booker" in out.getvalue()


def test_cli_refuses_a_user_pool_that_is_not_test_or_demo(table: Table) -> None:
    import boto3

    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    pool = cognito.create_user_pool(PoolName="homekeep-prod")["UserPool"]["Id"]
    code, out = _run(
        table,
        "--target",
        "aws",
        "--table-name",
        "homekeep-test",
        "--user-pool-id",
        pool,
        "--yes",
        "revoke",
        "--household",
        "qa-a",
        "--member",
        "hk-qa-a-booker",
    )
    assert code == 2
    assert "pool" in out
