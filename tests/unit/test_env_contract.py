from __future__ import annotations

import re
from pathlib import Path

from app import config
from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTRACT = REPO_ROOT / "docs" / "infra-contract.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _contract_rows() -> dict[str, set[str]]:
    """Variable name → environments in its "Required in" column, from contract §9."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("## 9 Environment variables", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, set[str]] = {}
    for line in section.splitlines():
        match = re.match(r"^\| `([A-Z][A-Z0-9_]*)` \| ([^|]*) \|", line)
        if match:
            required = match.group(2).strip()
            rows[match.group(1)] = (
                set() if required == "—" else {e.strip() for e in required.split(",")}
            )
    return rows


def _env_example_names() -> set[str]:
    names = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match:
            names.add(match.group(1))
    return names


def test_nfr10_env_example_matches_contract_and_settings() -> None:
    contract = _contract_rows()
    assert contract, "no variables parsed from docs/infra-contract.md §9"
    assert set(contract) == Settings.env_var_names()
    assert _env_example_names() == Settings.env_var_names()


def test_nfr10_contract_required_column_matches_settings() -> None:
    for name, envs in _contract_rows().items():
        expected = {
            env
            for env in ("local", "test", "demo")
            if name == "ENV" or name.lower() in config._REQUIRED_IN[env]
        }
        assert envs == expected, name
