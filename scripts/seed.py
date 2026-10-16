"""Seed synthetic households and identities (TDD §9.2; plan P1-2).

    uv run python -m scripts.seed --target local                 # DynamoDB Local (make seed)
    uv run python -m scripts.seed --target aws --env test|demo   # Deb only: Cognito + DynamoDB

The AWS target creates the Cognito users first (Cognito assigns each `sub`), adds staff to their
groups, then writes the DynamoDB items. New passwords are random and permanent (G1-1), printed once
to this terminal and never written anywhere else. Every write is create-if-missing, so re-running
changes nothing and never overwrites data a judge has added since.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

import boto3

from app.domain.appliances import Category, normalise
from app.domain.errors import ConflictError
from app.store import keys
from app.store.schema import ensure_table
from app.store.table import Table

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LOCAL_TABLE = "homekeep-local"
LOCAL_ENDPOINT = "http://localhost:8001"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "dynamodb-local"}
_PASSWORD_CLASSES = (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%^&*-_=+")


@dataclass
class SeedReport:
    created: int = 0
    existing: int = 0
    passwords: dict[str, str] = field(default_factory=dict)  # username -> new password


def load_fixtures() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    households = json.loads((FIXTURES / "households.json").read_text(encoding="utf-8"))
    identities = json.loads((FIXTURES / "identities.json").read_text(encoding="utf-8"))
    return households, identities["identities"]


def _in_env(record: dict[str, Any], env: str | None) -> bool:
    return env is None or env in record["envs"]


def local_subjects(identities: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Deterministic subjects for DynamoDB Local; the local token issuer uses the same ones."""
    return {identity["key"]: f"local-{identity['key']}" for identity in identities}


def household_items(
    household: dict[str, Any],
    members: Sequence[tuple[dict[str, Any], str]],
    seeded_at: str,
    consent_version: str,
) -> list[dict[str, Any]]:
    household_id = household["household_id"]
    pk = keys.household_pk(household_id)
    items: list[dict[str, Any]] = [
        {
            "PK": pk,
            "SK": keys.META,
            "kind": "HOUSEHOLD",
            "household_id": household_id,
            "locale": "en-IN",
            "timezone": "Asia/Kolkata",
            "lifecycle": "ACTIVE",
            "resettable": household["resettable"],
            "storage_consent": household["storage_consent"],
            "sharing_consent": household["sharing_consent"],
            "created_at": seeded_at,
            "updated_at": seeded_at,
            "version": 1,
        }
    ]
    for purpose in ("STORAGE", "SHARING"):
        decision = household[f"{purpose.lower()}_consent"]
        if decision:
            items.append(
                {
                    "PK": pk,
                    "SK": keys.consent_sk(purpose, seeded_at, "seed"),
                    "kind": "CONSENT",
                    "purpose": purpose,
                    "decision": decision,
                    "consent_version": consent_version,
                    "actor_sub": "seed",
                    "at": seeded_at,
                }
            )
    for appliance in household["appliances"]:
        category = Category(appliance["category"])
        nickname_key = normalise(appliance["nickname"])
        unknown = {"value": None, "status": "UNKNOWN", "provenance": None}
        items.append(
            {
                "PK": pk,
                "SK": keys.appliance_sk(appliance["appliance_id"]),
                "kind": "APPLIANCE",
                "appliance_id": appliance["appliance_id"],
                "category": category.value,
                "nickname": appliance["nickname"],
                "nickname_key": nickname_key,
                "room": appliance.get("room"),
                "fields": {
                    "brand": unknown,
                    "model": appliance.get("model", unknown),
                    "serial": unknown,
                },
                "conflicts": [],
                "created_at": seeded_at,
                "updated_at": seeded_at,
                "version": 1,
            }
        )
        items.append(
            {
                "PK": pk,
                "SK": keys.nickname_sk(nickname_key),
                "kind": "NICKNAME",
                "appliance_id": appliance["appliance_id"],
                "nickname": appliance["nickname"],
            }
        )
    for identity, sub in members:
        items.append(
            {
                "PK": pk,
                "SK": keys.member_sk(sub),
                "kind": "MEMBERSHIP",
                "sub": sub,
                "role": identity["role"],
                "grants": identity["grants"],
                "status": identity["status"],
                "consent_version": consent_version,
                "created_at": seeded_at,
                "version": 1,
            }
        )
        items.append(
            {
                "PK": keys.user_pk(sub),
                "SK": keys.user_household_sk(household_id),
                "kind": "MEMBERSHIP_LOOKUP",
                "household_id": household_id,
            }
        )
    return items


def write_items(table: Table, items: Iterable[dict[str, Any]], report: SeedReport) -> None:
    for item in items:
        try:
            table.put_new(item)
            report.created += 1
        except ConflictError:
            report.existing += 1


def seed_dynamo(
    table: Table, env: str | None, subjects: dict[str, str], report: SeedReport
) -> None:
    households, identities = load_fixtures()
    for household in households["households"]:
        if not _in_env(household, env):
            continue
        members = [
            (identity, subjects[identity["key"]])
            for identity in identities
            if identity.get("household") == household["household_id"] and _in_env(identity, env)
        ]
        items = household_items(
            household, members, households["seeded_at"], households["consent_version"]
        )
        write_items(table, items, report)


def seed_local(table: Table) -> SeedReport:
    report = SeedReport()
    _, identities = load_fixtures()
    seed_dynamo(table, None, local_subjects(identities), report)
    return report


def generate_password(length: int = 20) -> str:
    """Random, and satisfies Cognito's default policy (upper, lower, digit, symbol)."""
    rng = secrets.SystemRandom()
    chars = [rng.choice(group) for group in _PASSWORD_CLASSES]
    everything = "".join(_PASSWORD_CLASSES)
    chars += [rng.choice(everything) for _ in range(length - len(chars))]
    rng.shuffle(chars)
    return "".join(chars)


def _sub(attributes: Iterable[dict[str, str]]) -> str:
    return next(a["Value"] for a in attributes if a["Name"] == "sub")


class SeedError(Exception):
    """The target is not ready or not the intended one; nothing has been written."""


_SHOWN_ONCE_HEADER = (
    "\nNew passwords, shown ONCE as each is set: store them in a password manager now.\n"
    "Never paste them into the repository; judge logins go only in the Devpost testing field.\n\n"
)


def _announce(out: TextIO, report: SeedReport, username: str, password: str) -> None:
    """Print a password the moment Cognito holds it, so a later failure cannot lose it."""
    if not report.passwords:
        out.write(_SHOWN_ONCE_HEADER)
    report.passwords[username] = password
    out.write(f"  {username.ljust(18)}  {password}\n")
    out.flush()


def preflight(
    cognito: Any, table: Table, user_pool_id: str, identities: Sequence[dict[str, Any]]
) -> None:
    """Check the table, the pool and every needed group exist before changing anything."""
    try:
        table.client.describe_table(TableName=table.name)
    except table.client.exceptions.ResourceNotFoundException as exc:
        raise SeedError(f"table {table.name!r} does not exist") from exc
    try:
        cognito.describe_user_pool(UserPoolId=user_pool_id)
    except cognito.exceptions.ResourceNotFoundException as exc:
        raise SeedError(f"user pool {user_pool_id!r} does not exist") from exc
    existing: set[str] = set()
    for page in cognito.get_paginator("list_groups").paginate(UserPoolId=user_pool_id):
        existing.update(group["GroupName"] for group in page["Groups"])
    needed = {group for identity in identities for group in identity.get("groups", [])}
    missing = sorted(needed - existing)
    if missing:
        raise SeedError(f"user pool is missing groups {missing} (contract §5.4)")


def provision_cognito(
    cognito: Any,
    user_pool_id: str,
    identities: Iterable[dict[str, Any]],
    reset: Collection[str] | None,
    report: SeedReport,
    out: TextIO,
) -> dict[str, str]:
    subjects: dict[str, str] = {}
    for identity in identities:
        username = identity["username"]
        try:
            user = cognito.admin_get_user(UserPoolId=user_pool_id, Username=username)
            sub = _sub(user["UserAttributes"])
            if reset is not None and (not reset or username in reset):
                password = generate_password()
                cognito.admin_set_user_password(
                    UserPoolId=user_pool_id, Username=username, Password=password, Permanent=True
                )
                _announce(out, report, username, password)
        except cognito.exceptions.UserNotFoundException:
            password = generate_password()
            created = cognito.admin_create_user(
                UserPoolId=user_pool_id,
                Username=username,
                TemporaryPassword=password,
                MessageAction="SUPPRESS",  # no email or SMS: these accounts have no contact details
            )
            sub = _sub(created["User"]["Attributes"])
            # Shown now: if making it permanent fails, it still works as the temporary password.
            _announce(out, report, username, password)
            cognito.admin_set_user_password(
                UserPoolId=user_pool_id, Username=username, Password=password, Permanent=True
            )
        for group in identity.get("groups", []):
            cognito.admin_add_user_to_group(
                UserPoolId=user_pool_id, Username=username, GroupName=group
            )
        subjects[identity["key"]] = sub
    return subjects


def seed_aws(
    cognito: Any,
    table: Table,
    user_pool_id: str,
    env: str,
    reset: Collection[str] | None = None,
    out: TextIO = sys.stdout,
) -> SeedReport:
    """`reset`: None keeps existing passwords; an empty collection rotates every selected user;
    otherwise only the named usernames are rotated."""
    report = SeedReport()
    _, identities = load_fixtures()
    selected = [identity for identity in identities if _in_env(identity, env)]
    unknown = sorted(set(reset or ()) - {identity["username"] for identity in selected})
    if unknown:
        raise SeedError(f"--reset-passwords names users not seeded in {env}: {unknown}")
    preflight(cognito, table, user_pool_id, selected)
    subjects = provision_cognito(cognito, user_pool_id, selected, reset, report, out)
    seed_dynamo(table, env, subjects, report)
    return report


def print_report(report: SeedReport, out: TextIO) -> None:
    out.write(f"Items created: {report.created}; already present: {report.existing}\n")
    if report.passwords:
        out.write(f"{len(report.passwords)} new password(s) were shown above, once.\n")
    else:
        out.write("No new passwords were set.\n")


def _local_table(endpoint_url: str, table_name: str) -> Table:
    host = urlsplit(endpoint_url).hostname
    if host not in _LOCAL_HOSTS:
        raise SystemExit(f"--target local only writes to DynamoDB Local, not {host!r}")
    client = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        endpoint_url=endpoint_url,
        aws_access_key_id="local",  # DynamoDB Local accepts any credentials
        aws_secret_access_key="local",  # noqa: S106 (a dummy value for the local emulator)
    )
    ensure_table(client, table_name)
    return Table(client, table_name)


def main(argv: Sequence[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("local", "aws"), required=True)
    parser.add_argument("--env", choices=("test", "demo"), help="required with --target aws")
    parser.add_argument("--endpoint-url", default=LOCAL_ENDPOINT, help="local target only")
    parser.add_argument("--table-name", default=None)
    parser.add_argument("--user-pool-id", default=os.environ.get("COGNITO_USER_POOL_ID"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument(
        "--reset-passwords",
        nargs="*",
        metavar="USERNAME",
        default=None,
        help="aws target only: rotate these users' passwords (all seeded users if none named)",
    )
    parser.add_argument("--yes", action="store_true", help="aws target only: confirm the target")
    args = parser.parse_args(argv)

    if args.target == "local":
        table = _local_table(args.endpoint_url, args.table_name or LOCAL_TABLE)
        print_report(seed_local(table), out)
        return 0

    table_name = args.table_name or os.environ.get("TABLE_NAME")
    if not args.env:
        parser.error("--env is required with --target aws")
    if not table_name or not args.user_pool_id:
        parser.error("--target aws needs TABLE_NAME and COGNITO_USER_POOL_ID (flags or env)")
    session = boto3.session.Session(region_name=args.region)
    cognito = session.client("cognito-idp")
    try:
        account = session.client("sts").get_caller_identity()["Account"]
        pool_name = cognito.describe_user_pool(UserPoolId=args.user_pool_id)["UserPool"]["Name"]
    except cognito.exceptions.ResourceNotFoundException:
        out.write(f"Seed refused: user pool {args.user_pool_id!r} does not exist.\n")
        return 1
    out.write(
        f"Target: account {account}, region {args.region}, user pool {pool_name} "
        f"({args.user_pool_id}), table {table_name}, env {args.env}\n"
    )
    suffix = f"-{args.env}"
    if not (table_name.endswith(suffix) and pool_name.endswith(suffix)):
        out.write(f"Seed refused: the table and pool names must end in {suffix!r} (contract §2).\n")
        return 2
    if not args.yes:
        out.write("Nothing written. Check the target above, then re-run with --yes.\n")
        return 1
    try:
        report = seed_aws(
            cognito,
            Table(session.client("dynamodb"), table_name),
            args.user_pool_id,
            args.env,
            args.reset_passwords,
            out,
        )
    except SeedError as exc:
        out.write(f"Seed refused: {exc}. Nothing was written.\n")
        return 1
    print_report(report, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
