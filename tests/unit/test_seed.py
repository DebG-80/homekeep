from __future__ import annotations

import io
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import boto3
import pytest

from app.domain.appliances import resolve_appliance
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.security.membership import resolve_actor
from app.security.tokens import VerifiedToken
from app.store import keys
from app.store.table import Table, from_dynamo
from scripts import seed

GROUPS = ("coordinator", "technician", "catalog_reviewer", "admin")


def _scan(table: Table) -> list[dict[str, Any]]:
    items = table.client.scan(TableName=table.name)["Items"]
    return sorted((from_dynamo(i) for i in items), key=lambda i: (i["PK"], i["SK"]))


def _pool() -> tuple[Any, str]:
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    pool_id = cognito.create_user_pool(PoolName="homekeep-unit")["UserPool"]["Id"]
    for group in GROUPS:
        cognito.create_group(UserPoolId=pool_id, GroupName=group)
    return cognito, pool_id


def test_seed_local_is_idempotent_and_matches_brd_12_1(table: Table) -> None:
    first = seed.seed_local(table)
    assert first.created > 0
    assert first.existing == 0
    snapshot = _scan(table)

    appliances = table.query(keys.household_pk("qa-a"), keys.APPLIANCE_PREFIX)
    assert Counter(a["category"] for a in appliances) == {
        "AC": 2,
        "REFRIGERATOR": 1,
        "TELEVISION": 1,
    }
    assert {a["room"] for a in appliances if a["category"] == "AC"} == {"bedroom", "hall"}
    members = {m["sub"]: m for m in table.query(keys.household_pk("qa-a"), keys.MEMBER_PREFIX)}
    assert {(m["role"], m["status"], tuple(m["grants"])) for m in members.values()} == {
        ("OWNER", "ACTIVE", ("view", "edit", "book", "updates")),
        ("HELPER", "ACTIVE", ("view",)),
        ("HELPER", "ACTIVE", ("view", "edit", "book", "updates")),
        ("HELPER", "REVOKED", ("view", "book")),
    }
    b_meta = table.get(keys.household_pk("qa-b"), keys.META)
    assert (b_meta["storage_consent"], b_meta["sharing_consent"]) == ("GRANTED", "DECLINED")
    for judge in ("judge-1", "judge-2", "judge-3"):  # G1-2: judges start from consent
        meta = table.get(keys.household_pk(judge), keys.META)
        assert (meta["storage_consent"], meta["resettable"]) == (None, True)
        assert table.query(keys.household_pk(judge), keys.APPLIANCE_PREFIX) == []
    assert table.query(keys.user_pk("local-coordinator")) == []  # staff have no household

    # The seeded records work with the real membership lookup and domain services.
    owner = resolve_actor(table, VerifiedToken("local-a_owner", "web", frozenset(), frozenset()))
    ctx = OperationContext(owner, table, SystemClock(), "corr-seed")
    assert resolve_appliance(ctx, "my AC")["needs_clarification"] is True

    second = seed.seed_local(table)
    assert (second.created, second.existing) == (0, first.created)
    assert _scan(table) == snapshot  # re-running changes nothing


def test_seed_aws_creates_cognito_users_groups_and_memberships(table: Table) -> None:
    cognito, pool_id = _pool()
    report = seed.seed_aws(cognito, table, pool_id, env="demo")

    users = {u["Username"] for u in cognito.list_users(UserPoolId=pool_id)["Users"]}
    assert users == {"hk-judge-1", "hk-judge-2", "hk-judge-3", "hk-tech-1", "hk-coordinator"}
    assert set(report.passwords) == users
    groups = cognito.admin_list_groups_for_user(UserPoolId=pool_id, Username="hk-coordinator")
    assert [g["GroupName"] for g in groups["Groups"]] == ["coordinator"]
    assert (
        cognito.admin_get_user(UserPoolId=pool_id, Username="hk-judge-1")["UserStatus"]
        == "CONFIRMED"
    )

    # The membership is keyed by the sub Cognito assigned, and resolves to the judge household.
    attributes = cognito.admin_get_user(UserPoolId=pool_id, Username="hk-judge-1")["UserAttributes"]
    sub = next(a["Value"] for a in attributes if a["Name"] == "sub")
    actor = resolve_actor(table, VerifiedToken(sub, "web", frozenset(), frozenset()))
    assert actor.household_id == "judge-1"
    assert table.get(keys.household_pk("qa-a"), keys.META) is None  # QA data stays off demo

    again = seed.seed_aws(cognito, table, pool_id, env="demo")
    assert (again.created, again.passwords) == (0, {})
    reset = seed.seed_aws(cognito, table, pool_id, env="demo", reset=[])  # [] = everyone
    assert set(reset.passwords) == users
    assert reset.passwords["hk-judge-1"] != report.passwords["hk-judge-1"]


def test_inv9_passwords_printed_once_never_written_and_fixtures_synthetic(
    table: Table, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cognito, pool_id = _pool()
    out = io.StringIO()
    seed.print_report(seed.seed_aws(cognito, table, pool_id, env="test", out=out), out)
    printed = out.getvalue()

    passwords = re.findall(r"^  hk-\S+\s+(\S+)$", printed, flags=re.MULTILINE)
    assert len(passwords) == 13
    stored = json.dumps(_scan(table))
    for password in passwords:
        assert printed.count(password) == 1  # shown once
        assert password not in stored  # never in DynamoDB
        assert len(password) >= 12
        for character_class in (r"[A-Z]", r"[a-z]", r"\d", r"[^A-Za-z0-9]"):
            assert re.search(character_class, password), character_class
    assert os.listdir(tmp_path) == []  # nothing written to disk

    rerun = io.StringIO()
    seed.print_report(seed.seed_aws(cognito, table, pool_id, env="test", out=rerun), rerun)
    assert "No new passwords were set." in rerun.getvalue()

    for fixture in ("households.json", "identities.json"):
        text = (seed.FIXTURES / fixture).read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", text), fixture  # no email addresses
        assert not re.search(r"\d{10,}", text), fixture  # no phone or account numbers
        assert "password" not in text.casefold(), fixture
    usernames = [i["username"] for i in seed.load_fixtures()[1]]
    assert all(u.startswith("hk-") for u in usernames)


def test_local_target_refuses_non_local_endpoints() -> None:
    with pytest.raises(SystemExit, match="only writes to DynamoDB Local"):
        seed.main(
            ["--target", "local", "--endpoint-url", "https://dynamodb.us-east-1.amazonaws.com"]
        )
    with pytest.raises(SystemExit):
        seed.main(["--target", "aws"])  # --env is required


def test_seed_aws_prints_each_password_before_any_later_failure(
    table: Table, monkeypatch: pytest.MonkeyPatch
) -> None:
    cognito, pool_id = _pool()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("DynamoDB write failed")

    monkeypatch.setattr(seed, "seed_dynamo", fail)
    out = io.StringIO()
    with pytest.raises(RuntimeError):
        seed.seed_aws(cognito, table, pool_id, env="demo", out=out)

    # Every user Cognito accepted already had its password shown; nothing is lost.
    shown = dict(re.findall(r"^  (hk-\S+)\s+(\S+)$", out.getvalue(), flags=re.MULTILINE))
    created = {u["Username"] for u in cognito.list_users(UserPoolId=pool_id)["Users"]}
    assert set(shown) == created
    assert len(created) == 5


def test_seed_aws_preflight_refuses_before_creating_users(table: Table) -> None:
    cognito, pool_id = _pool()
    cognito.delete_group(UserPoolId=pool_id, GroupName="technician")
    with pytest.raises(seed.SeedError, match="technician"):
        seed.seed_aws(cognito, table, pool_id, env="demo", out=io.StringIO())
    assert cognito.list_users(UserPoolId=pool_id)["Users"] == []

    cognito.create_group(UserPoolId=pool_id, GroupName="technician")
    missing_table = Table(table.client, "homekeep-missing")
    with pytest.raises(seed.SeedError, match="homekeep-missing"):
        seed.seed_aws(cognito, missing_table, pool_id, env="demo", out=io.StringIO())
    assert cognito.list_users(UserPoolId=pool_id)["Users"] == []


def test_seed_aws_resets_only_named_users(table: Table) -> None:
    cognito, pool_id = _pool()
    first = seed.seed_aws(cognito, table, pool_id, env="demo", out=io.StringIO())

    out = io.StringIO()
    rotated = seed.seed_aws(cognito, table, pool_id, env="demo", reset=["hk-judge-2"], out=out)
    assert set(rotated.passwords) == {"hk-judge-2"}  # judge logins already in Devpost survive
    assert rotated.passwords["hk-judge-2"] != first.passwords["hk-judge-2"]
    assert "hk-judge-1" not in out.getvalue()
    with pytest.raises(seed.SeedError, match="hk-nobody"):
        seed.seed_aws(cognito, table, pool_id, env="demo", reset=["hk-nobody"], out=io.StringIO())


def test_seed_aws_main_shows_target_and_requires_yes_and_env_names(table: Table) -> None:
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    pool_id = cognito.create_user_pool(PoolName="homekeep-test")["UserPool"]["Id"]
    for group in GROUPS:
        cognito.create_group(UserPoolId=pool_id, GroupName=group)
    seed.ensure_table(table.client, "homekeep-test")
    base = ["--target", "aws", "--table-name", "homekeep-test", "--user-pool-id", pool_id]

    out = io.StringIO()
    assert seed.main([*base, "--env", "test"], out) == 1  # shows the target, writes nothing
    shown = out.getvalue()
    assert "homekeep-test" in shown
    assert pool_id in shown
    assert "account" in shown.casefold()
    assert "--yes" in shown
    assert cognito.list_users(UserPoolId=pool_id)["Users"] == []

    # --env demo against the test pool and table is refused even with --yes.
    assert seed.main([*base, "--env", "demo", "--yes"], io.StringIO()) == 2
    assert cognito.list_users(UserPoolId=pool_id)["Users"] == []

    assert seed.main([*base, "--env", "test", "--yes"], io.StringIO()) == 0
    assert len(cognito.list_users(UserPoolId=pool_id)["Users"]) == 13
