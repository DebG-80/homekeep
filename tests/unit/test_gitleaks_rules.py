"""The custom gitleaks rules catch real AWS identifiers and leave placeholders alone.

The rule regexes are RE2 syntax that Python's `re` also accepts, so they can be exercised
here without the gitleaks binary. Sample identifiers are assembled at runtime so that this
file itself never contains one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POOL_RULE = "homekeep-cognito-user-pool-id"
ARN_RULE = "homekeep-aws-account-id-in-arn"
ECR_RULE = "homekeep-aws-account-id-in-ecr-uri"


def _rules() -> dict[str, re.Pattern[str]]:
    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    return {rule["id"]: re.compile(rule["regex"]) for rule in config["rules"]}


def _fake_account() -> str:
    return "".join(str(d) for d in (4, 2, 7, 1, 9, 3, 0, 5, 8, 6, 1, 2))


def test_inv9_custom_rules_catch_pool_ids_and_account_arns() -> None:
    rules = _rules()
    pool_ids = [
        "us-east-1" + "_" + "Ab3dE" + "fGh1",
        "ap-south-1" + "_" + "ZZZZ" + "99999",
        "us-gov-west-1" + "_" + "abcd" + "efghi",
    ]
    for pool_id in pool_ids:
        assert rules[POOL_RULE].search(f"COGNITO_USER_POOL_ID={pool_id}"), pool_id

    account = _fake_account()
    arns = [
        f"arn:aws:iam::{account}:role/homekeep-demo-task",
        f"arn:aws:dynamodb:us-east-1:{account}:table/homekeep-demo",
        f"arn:aws:cognito-idp:us-east-1:{account}:userpool/x",
        f'"Resource": "arn:aws:bedrock:us-east-1:{account}:inference-profile/us.x"',
    ]
    for arn in arns:
        assert rules[ARN_RULE].search(arn), arn


def test_inv9_custom_rule_catches_account_ids_in_ecr_uris() -> None:
    rules = _rules()
    account = _fake_account()
    registries = [
        f"docker push {account}.dkr.ecr.us-east-1.amazonaws.com/homekeep:abc123",
        f"{account}.dkr.ecr-fips.us-east-1.amazonaws.com",
    ]
    for registry in registries:
        assert rules[ECR_RULE].search(registry), registry


def test_inv9_placeholders_are_not_flagged() -> None:
    rules = _rules()
    placeholders = [
        "COGNITO_USER_POOL_ID=<COGNITO_USER_POOL_ID>",
        "us-east-1_placeholder",  # longer than a real pool ID
        "us-east-1_short",
        "arn:aws:iam::${ACCOUNT_ID}:role/homekeep-demo-task",
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${TABLE_NAME}",
        "arn:aws:dynamodb:us-east-1:<ACCOUNT_ID>:table/homekeep-demo",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:s3:::${BUCKET_NAME}/quarantine/*",
        "<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/homekeep:<GIT_SHA>",
        "${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com",
    ]
    for text in placeholders:
        for rule_id, pattern in rules.items():
            assert not pattern.search(text), (rule_id, text)

    # The files that describe provisioning must hold placeholders only.
    for relative in ("docs/infra-contract.md", ".env.example", "compose.yaml"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for rule_id, pattern in rules.items():
            assert not pattern.search(text), (rule_id, relative)
