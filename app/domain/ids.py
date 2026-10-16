"""Opaque identifiers (BRD §8.2), meaningless outside HomeKeep.

`new_id` is random. `ordered_id` has a time-ordered prefix and is used only inside sort keys
(events, consent records) so they list in write order; its random suffix keeps it unguessable.
"""

from __future__ import annotations

import itertools
import secrets
import time

_SEQUENCE = itertools.count()


def new_id() -> str:
    return secrets.token_hex(12)


def ordered_id() -> str:
    """Sorts in write order even when the injected clock is fixed (CLOCK_OVERRIDE, P1-3): the
    real wall clock plus a process counter break ties, then a random suffix keeps it opaque."""
    return f"{time.time_ns():019d}{next(_SEQUENCE) % 10_000:04d}{new_id()[:8]}"
