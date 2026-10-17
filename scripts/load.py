"""Load smoke run (TDD §1.3, §12.1; NFR-01, NFR-09; plan G4-11): concurrent sessions, each
sending turns through the turn API, with latency and correlation evidence.

    make run
    uv run python -m scripts.load --base-url http://localhost:8000 --sessions 3 --turns 34

Locally it signs in judge households through `/local/token`. Against AWS, pass access tokens
with `--token-file` (one per line, never committed). The formal AT-29 run is deferred (P1-1).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TextIO

import httpx

PHRASES = (
    "Hello",
    "What appliances do I have?",
    "Please repeat that",
    "Speak slower please",
)
LOCAL_IDENTITIES = ("j1_owner", "j2_owner", "j3_owner")


def _session(base_url: str, token: str, turns: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base_url, headers=headers, timeout=60) as client:
        session_id = client.post("/api/sessions").raise_for_status().json()["session_id"]
        for index in range(turns):
            body = {
                "session_id": session_id,
                "turn_id": f"load-{uuid.uuid4().hex[:12]}",
                "text": PHRASES[index % len(PHRASES)],
            }
            started = time.perf_counter()
            try:
                response = client.post("/api/turns", json=body)
                data = response.json() if response.status_code == 200 else {}
                status = response.status_code
            except httpx.HTTPError:
                data, status = {}, 0
            samples.append(
                {
                    "ms": (time.perf_counter() - started) * 1000,
                    "status": status,
                    "correlation_id": data.get("correlation_id"),
                    "handled_by": data.get("handled_by"),
                }
            )
    return samples


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def run_load(base_url: str, tokens: Sequence[str], turns: int) -> dict[str, Any]:
    """One concurrent session per token, `turns` turns each."""
    with ThreadPoolExecutor(max_workers=len(tokens)) as pool:
        results = list(pool.map(lambda token: _session(base_url, token, turns), tokens))
    samples = [sample for session in results for sample in session]
    latencies = [s["ms"] for s in samples]
    correlations = [s["correlation_id"] for s in samples]
    return {
        "sessions": len(tokens),
        "turns": len(samples),
        "errors": sum(1 for s in samples if s["status"] != 200),
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1),
            "p95": round(_percentile(latencies, 0.95), 1),
            "max": round(max(latencies), 1),
        },
        "correlation_complete": all(correlations) and len(set(correlations)) == len(samples),
        "handled_by": dict(Counter(s["handled_by"] for s in samples)),
    }


def _local_tokens(base_url: str, count: int) -> list[str]:
    tokens = []
    for identity in LOCAL_IDENTITIES[:count]:
        minted = httpx.post(f"{base_url}/local/token", json={"identity": identity}, timeout=10)
        tokens.append(minted.raise_for_status().json()["access_token"])
    return tokens


def main(argv: Sequence[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--turns", type=int, default=34)
    parser.add_argument("--token-file", type=Path, help="AWS: one access token per line")
    args = parser.parse_args(argv)
    if args.token_file:
        tokens = [t for t in args.token_file.read_text(encoding="utf-8").split() if t]
    else:
        tokens = _local_tokens(args.base_url, args.sessions)
    report = run_load(args.base_url, tokens[: args.sessions], args.turns)
    out.write(json.dumps(report, indent=2) + "\n")
    return 0 if report["errors"] == 0 and report["correlation_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
