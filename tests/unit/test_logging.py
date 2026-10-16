from __future__ import annotations

import json
import logging

import pytest

from app.logging import hash_subject, log_event


def test_nfr07_logs_keep_only_allowlisted_fields(capsys: pytest.CaptureFixture[str]) -> None:
    from app.logging import configure_logging

    configure_logging("INFO")
    log_event(
        "TOOL_CALL",
        correlation_id="corr-1",
        sub="sub-secret-subject",
        role="OWNER",
        action="register_appliance",
        result="OK",
        latency_ms=12,
        transcript="my address is 12 Example Street",  # never logged
        address="12 Example Street",
        token="eyJhbGciOi...",  # noqa: S106 (test input that must be dropped)
        email="someone@example.com",
    )
    (line,) = capsys.readouterr().err.strip().splitlines()
    payload = json.loads(line)
    assert payload == {
        "event": "TOOL_CALL",
        "correlation_id": "corr-1",
        "actor": hash_subject("sub-secret-subject"),
        "role": "OWNER",
        "action": "register_appliance",
        "result": "OK",
        "latency_ms": 12,
    }
    assert "sub-secret-subject" not in line


def test_nfr07_app_configures_json_logging_at_log_level(capsys: pytest.CaptureFixture[str]) -> None:
    from app.config import Settings
    from app.logging import LOGGER, log_error
    from app.main import create_app

    create_app(
        Settings.from_env(
            {"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://x", "LOG_LEVEL": "INFO"}
        )
    )
    assert LOGGER.getEffectiveLevel() == logging.INFO
    log_event("TURN", correlation_id="corr-2", result="OK")
    try:
        raise RuntimeError("boom with a secret transcript")
    except RuntimeError as exc:
        log_error("TOOL_FAILED", exc, correlation_id="corr-3")
    lines = [json.loads(line) for line in capsys.readouterr().err.strip().splitlines()]
    assert {"event": "TURN", "correlation_id": "corr-2", "result": "OK"} in lines
    failure = next(line for line in lines if line["event"] == "TOOL_FAILED")
    assert failure == {
        "event": "TOOL_FAILED",
        "correlation_id": "corr-3",
        "error_code": "RuntimeError",
    }


def test_nfr07_each_log_line_is_written_once() -> None:
    # FastMCP puts a handler on the root logger; HomeKeep lines must not also propagate there.
    from app.config import Settings
    from app.logging import LOGGER
    from app.main import create_app

    create_app(Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://x"}))
    create_app(Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://x"}))
    assert LOGGER.propagate is False
    ours = [h for h in LOGGER.handlers if type(h).__name__ == "_StderrHandler"]
    assert len(ours) == 1  # building the app twice must not add a second writer
