from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_image_ships_the_catalog_and_fixtures_the_app_reads() -> None:
    # Guidance reads catalog_data/ at runtime; local sign-in reads fixtures/identities.json.
    # Without them in the image, every guidance call on AWS would be RETRIEVAL_FAILURE.
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for directory in ("app", "catalog_data", "fixtures"):
        assert f"!{directory}/" in dockerignore, directory
        assert re.search(rf"^COPY {directory}/ \./{directory}/$", dockerfile, re.MULTILINE), (
            directory
        )


def test_access_log_is_off_so_urls_never_reach_the_logs() -> None:
    # Request paths carry opaque record IDs; TDD §10.2 allows only allowlisted, structured fields.
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    cmd = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    assert "--no-access-log" in cmd
