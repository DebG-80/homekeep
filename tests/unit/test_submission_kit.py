from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBMISSION = REPO_ROOT / "docs" / "submission"

KIT_FILES = (
    SUBMISSION / "description.md",
    SUBMISSION / "built-with.md",
    SUBMISSION / "testing-instructions.md",
    SUBMISSION / "feature-requests.md",
    SUBMISSION / "video-script.md",
    SUBMISSION / "checklist.md",
    REPO_ROOT / "docs" / "product-feedback.md",
)

FEEDBACK_TOOLS = (
    "Amazon Bedrock",
    "Strands Agents SDK",
    "Amazon DynamoDB (including DynamoDB Local)",
    "Amazon S3",
    "Amazon Cognito",
    "Amazon ECS Express Mode (Fargate + ALB)",
    "Amazon ECR",
    "AWS IAM",
    "Amazon CloudWatch Logs",
    "AWS Budgets",
    "Alexa+ (MCP integration docs)",
    "MCP Python SDK",
    "MCP Inspector",
)

FIVE_QUESTIONS = (
    "**What did you use it for?**",
    "**What worked well?**",
    "**What needs improvement?**",
    "**How was onboarding?**",
    "**Would you build with it again?**",
)


def test_br07_submission_kit_files_present() -> None:
    for path in KIT_FILES:
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").startswith("# "), path


def test_br07_product_feedback_has_five_questions_per_tool() -> None:
    text = (REPO_ROOT / "docs" / "product-feedback.md").read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    by_tool = {section.split("\n", 1)[0].strip(): section for section in sections}

    assert tuple(by_tool) == FEEDBACK_TOOLS
    for tool, body in by_tool.items():
        assert "**Integration point in code:**" in body, tool
        for question in FIVE_QUESTIONS:
            assert body.count(question) == 1, (tool, question)


def test_inv9_testing_instructions_hold_no_credentials() -> None:
    text = (SUBMISSION / "testing-instructions.md").read_text(encoding="utf-8")
    assert "**Credentials are entered only in the Devpost field. Never paste them here.**" in text

    labelled = re.findall(
        r"\b(?:password|username|user name|e-?mail)\s*:\s*([^/|\n]*)", text, flags=re.IGNORECASE
    )
    assert labelled, "expected placeholder credential rows"
    for value in labelled:
        assert re.fullmatch(r"<[A-Z0-9_]+>", value.strip().strip("`")), value

    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "email address in testing instructions"
