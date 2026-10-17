"""hk-admin: audited operator commands for HomeKeep test and demo data (TDD §4.10; plan P4-2).

    uv run python -m scripts.hk_admin --target local reset --household judge-1
    uv run python -m scripts.hk_admin --target aws --table-name homekeep-test \\
        --user-pool-id <POOL> revoke --household qa-a --member hk-qa-a-booker --yes

Commands: reset, purge, grant, revoke, catalog withdraw|restore, fault set|clear. Each runs
through the same domain functions as the app and writes an audit record attributed to
`admin:cli`. The AWS target refuses tables whose names do not end in -test or -demo and writes
nothing without --yes. Run it with your own credentials, never the task role.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Callable, Sequence
from typing import TextIO

import boto3

from app.admin import operations, purge
from app.domain import members
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.domain.errors import DomainError, ErrorCode
from app.security.actor import Actor, ActorKind, Grant
from app.store import keys
from app.store.table import Table
from scripts.seed import LOCAL_ENDPOINT, LOCAL_TABLE, local_table

ACTOR = "admin:cli"
_SUFFIXES = ("-test", "-demo")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hk-admin", description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("local", "aws"), required=True)
    parser.add_argument("--endpoint-url", default=LOCAL_ENDPOINT, help="local target only")
    parser.add_argument("--table-name", default=None)
    parser.add_argument("--user-pool-id", default=os.environ.get("COGNITO_USER_POOL_ID"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--yes", action="store_true", help="aws target only: confirm the target")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("reset", "purge"):
        command = commands.add_parser(name)
        command.add_argument("--household", required=True)
    grant = commands.add_parser("grant")
    grant.add_argument("--household", required=True)
    grant.add_argument("--member", required=True, help="the member's sign-in name")
    grant.add_argument("--grants", required=True, help="comma-separated: view,edit,book,updates")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--household", required=True)
    revoke.add_argument("--member", required=True, help="the member's sign-in name")

    catalog = commands.add_parser("catalog").add_subparsers(dest="action", required=True)
    withdraw = catalog.add_parser("withdraw")
    withdraw.add_argument("item")
    withdraw.add_argument("--reason", required=True)
    catalog.add_parser("restore").add_argument("item")

    fault = commands.add_parser("fault").add_subparsers(dest="action", required=True)
    fault_set = fault.add_parser("set")
    fault_set.add_argument("--household", required=True)
    fault_set.add_argument("--fault", required=True)
    fault_set.add_argument("--remaining", type=int, default=1)
    fault.add_parser("clear").add_argument("--household", required=True)
    return parser


def _operator(table: Table, household_id: str) -> OperationContext:
    actor = Actor(
        sub=ACTOR,
        kind=ActorKind.OPERATOR,
        household_id=household_id,
        grants=frozenset(Grant),
    )
    return OperationContext(
        actor, table, SystemClock(), f"corr-cli-{uuid.uuid4().hex}", turn_id="cli"
    )


def _member_ref(table: Table, household_id: str, display_name: str) -> str:
    for member in table.query(keys.household_pk(household_id), keys.MEMBER_PREFIX):
        if member.get("display_name") == display_name:
            return members.member_ref(household_id, str(member["sub"]))
    raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")


def _cognito_sign_out(pool_id: str | None, region: str, out: TextIO) -> Callable[[str], None]:
    if not pool_id:
        return lambda username: out.write(f"  (no user pool given: {username} not signed out)\n")
    cognito = boto3.client("cognito-idp", region_name=region)
    return lambda username: cognito.admin_user_global_sign_out(
        UserPoolId=pool_id, Username=username
    )


def _sign_out_all(sign_out: Callable[[str], None], usernames: list[str], out: TextIO) -> int:
    """Sign each user out of Cognito. The data change already stands; a failure is reported,
    not raised, so the operator knows exactly whom to sign out by hand."""
    failed = []
    for username in usernames:
        try:
            sign_out(username)
        except Exception:
            failed.append(username)
    done = [u for u in usernames if u not in failed]
    out.write(f"Signed out: {', '.join(done) or 'nobody'}.\n")
    if failed:
        out.write(
            f"NOT signed out: {', '.join(failed)}. Sign them out in the Cognito console "
            "(their access has already ended).\n"
        )
        return 1
    return 0


def _execute(
    args: argparse.Namespace, table: Table, sign_out: Callable[[str], None], out: TextIO
) -> int:
    clock = SystemClock()
    if args.command == "reset":
        report = purge.reset_household(table, clock, args.household, actor_label=ACTOR)
        out.write(
            f"Reset {args.household}: {report.deleted} removed, {report.restored} restored, "
            f"{report.released_places} slot place(s) released.\n"
        )
    elif args.command == "purge":
        report = purge.purge_household(table, clock, args.household, actor_label=ACTOR)
        out.write(f"Purged {args.household}: {report.deleted} removed.\n")
        return _sign_out_all(sign_out, report.signed_out, out)
    elif args.command == "grant":
        ref = _member_ref(table, args.household, args.member)
        view = members.set_grants(
            _operator(table, args.household), ref, [g.strip() for g in args.grants.split(",")]
        )
        out.write(f"{args.member} now has: {', '.join(view['grants'])}.\n")
    elif args.command == "revoke":
        ref = _member_ref(table, args.household, args.member)
        _, username = members.revoke(_operator(table, args.household), ref)
        out.write(f"{args.member} is revoked.\n")
        return _sign_out_all(sign_out, [username], out)
    elif args.command == "catalog" and args.action == "withdraw":
        operations.withdraw_item(table, clock, args.item, args.reason, ACTOR)
        out.write(f"{args.item} withdrawn.\n")
    elif args.command == "catalog":
        operations.restore_item(table, clock, args.item, ACTOR)
        out.write(f"{args.item} restored to its published status.\n")
    elif args.command == "fault" and args.action == "set":
        operations.set_fault(table, clock, args.household, args.fault, args.remaining, ACTOR)
        out.write(f"Fault {args.fault} set for {args.household} ({args.remaining} use(s)).\n")
    else:
        operations.clear_fault(table, clock, args.household, ACTOR)
        out.write(f"Fault cleared for {args.household}.\n")
    return 0


def main(
    argv: Sequence[str] | None = None,
    out: TextIO = sys.stdout,
    *,
    table: Table | None = None,
    sign_out: Callable[[str], None] | None = None,
) -> int:
    """`table` and `sign_out` are injected by tests; otherwise they come from the target."""
    args = _parser().parse_args(argv)
    if args.target == "local":
        table = table or local_table(args.endpoint_url, args.table_name or LOCAL_TABLE)
        sign_out = sign_out or (lambda username: None)  # no Cognito locally
    else:
        table_name = args.table_name or os.environ.get("TABLE_NAME")
        if not table_name or not table_name.endswith(_SUFFIXES):
            out.write(
                "hk-admin refused: the table name must end in -test or -demo (contract §2).\n"
            )
            return 2
        out.write(f"Target: table {table_name}, region {args.region}, command {args.command}\n")
        if args.user_pool_id:
            cognito = boto3.client("cognito-idp", region_name=args.region)
            pool = cognito.describe_user_pool(UserPoolId=args.user_pool_id)["UserPool"]["Name"]
            if not pool.endswith(table_name[table_name.rindex("-") :]):
                out.write(f"hk-admin refused: user pool {pool!r} does not match the table.\n")
                return 2
        if not args.yes:
            out.write("Nothing written. Check the target above, then re-run with --yes.\n")
            return 1
        table = table or Table(boto3.client("dynamodb", region_name=args.region), table_name)
        sign_out = sign_out or _cognito_sign_out(args.user_pool_id, args.region, out)
    try:
        return _execute(args, table, sign_out, out)
    except DomainError as error:
        out.write(f"hk-admin refused: {error.reason}.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
