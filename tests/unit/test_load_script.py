"""The load smoke script (TDD §12.1; plan G4-11): concurrent sessions against a base URL."""

from __future__ import annotations

from app.security.local_issuer import LocalIssuer
from app.store.table import Table
from scripts import load, seed
from scripts.inprocess import serve


def test_load_reports_latency_and_correlation(table: Table, issuer: LocalIssuer) -> None:
    seed.seed_local(table)
    with serve(table, issuer) as live:
        tokens = [live.token("j1_owner"), live.token("j2_owner")]
        report = load.run_load(live.base_url, tokens, turns=3)
    assert (report["sessions"], report["turns"], report["errors"]) == (2, 6, 0)
    assert report["correlation_complete"] is True  # every turn carries a unique correlation ID
    latency = report["latency_ms"]
    assert 0 < latency["p50"] <= latency["p95"] <= latency["max"]
    assert sum(report["handled_by"].values()) == 6
