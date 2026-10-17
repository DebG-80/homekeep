from __future__ import annotations

import re

from app.channel import templates


def test_templates_follow_elder_voice_rules() -> None:
    texts = [
        *templates.COMMANDS.values(),
        templates.OUTPUT_GUARD_FALLBACK,
        templates.CYCLE_CAP,
        templates.DAILY_CAP,
        templates.TURN_ERROR,
        templates.GUIDANCE_FOLLOW_UP,
        templates.DEMO_DISCLOSURE,
    ]
    for text in texts:
        sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
        assert len(sentences) <= 2, text
        assert text.count("?") <= 1, text
        assert not re.search(r"\d|https?://|_", text), text
        assert "free" not in text.casefold(), text
        for claim in ("booked", "confirmed", "scheduled"):
            assert claim not in text.casefold(), text
        if "technician" in text.casefold():
            assert "demo" in text.casefold(), text
    assert "No real technician will visit" in templates.DEMO_DISCLOSURE


FACTS = {
    "kind": "SUBMIT",
    "provider": "HomeKeep Demo Service Desk",
    "date": "2026-10-17",
    "date_words": "Saturday, 17 October",
    "window_words": "10 am and 1 pm",
    "fee_paise": 49900,
    "fee_status": "ESTIMATE",
    "warranty": "UNKNOWN",
    "address": "Flat 4, Example Residency, Pune",
    "contact": "Landline 000 0000 0000",
    "data_shared": [],
    "demo": True,
}


def _chunk_rules(chunks: list[str]) -> None:
    for chunk in chunks:
        sentences = [s for s in re.split(r"(?<=[.?!])\s+", chunk.strip()) if s]
        assert len(sentences) <= 2, chunk
        assert chunk.count("?") <= 1, chunk
        assert "free" not in chunk.casefold(), chunk


def test_fr12_readback_names_every_material_item() -> None:
    spoken = " ".join(templates.render_readback(FACTS))
    for item in (
        "HomeKeep Demo Service Desk",
        "Saturday, 17 October",
        "10 am and 1 pm",
        "499 rupees",
        "estimate",
        "warranty is not known",
        "Flat 4, Example Residency, Pune",
        "Landline 000 0000 0000",
        "demonstration",
        "no real technician will visit",
        "Shall I book it?",
    ):
        assert item.casefold() in spoken.casefold(), item
    assert spoken.endswith("Shall I book it?")
    _chunk_rules(templates.render_readback(FACTS))
    unknown = " ".join(
        templates.render_readback({**FACTS, "fee_paise": None, "fee_status": "UNKNOWN"})
    )
    assert "the fee is not known yet" in unknown.casefold()  # unknown is never "free"
    for kind in ("RESCHEDULE", "CANCEL", "CONSENT_STORAGE", "CONSENT_SHARING"):
        _chunk_rules(templates.render_readback({**FACTS, "kind": kind, "purpose": "STORAGE"}))


def test_inv6_outcomes_spoken_from_templates_with_demo_disclosure() -> None:
    appointment = {"date_words": "Saturday, 17 October", "window_words": "10 am and 1 pm"}
    for outcome in templates.OUTCOMES:
        chunks = templates.render_outcome(
            {"outcome": outcome, "appointment": appointment, "fee_paise": 59900}
        )
        _chunk_rules(chunks)
        spoken = " ".join(chunks).casefold()
        if outcome in ("CONFIRMED", "CHANGED"):
            assert "demo" in spoken, outcome
            assert "no real technician will visit" in spoken, outcome
            assert "saturday, 17 october" in spoken, outcome
        if outcome in ("PENDING", "REQUESTED", "CANCEL_PENDING"):
            assert "pending" in spoken, outcome
            assert "confirmed" not in spoken, outcome
            assert "cancelled" not in spoken, outcome


def test_resolution_and_history_replies_follow_elder_voice_rules() -> None:
    for answer, closed, visit in (
        ("RESOLVED", False, False),
        ("RESOLVED", True, True),
        ("PERSISTS", False, False),
        ("UNSURE", False, False),
    ):
        chunks = templates.render_resolution(
            {"answer": answer, "closed": closed, "uncancelled_visit": visit}
        )
        _chunk_rules(chunks)
        if visit:
            assert "demo visit" in " ".join(chunks)
    entries = [
        {"action": "ISSUE_REPORTED", "date_words": "Friday, 16 October", "actor_role": "OWNER"},
        {"action": "SERVICE_CONFIRMED", "date_words": "Friday, 16 October", "actor_role": "OWNER"},
        {
            "action": "STAFF_VISIT_COMPLETED",
            "date_words": "Saturday, 17 October",
            "actor_role": "technician",
        },
    ]
    chunks = templates.render_history({"appliance": "Bedroom AC", "entries": entries})
    _chunk_rules(chunks)
    spoken = " ".join(chunks)
    assert "Bedroom AC" in spoken
    assert "Saturday, 17 October" in spoken
    assert "technician" in spoken


def test_review_readbacks_end_with_one_question_and_name_the_provider() -> None:
    for kind in ("RESCHEDULE", "CANCEL", "CONSENT_STORAGE", "CONSENT_SHARING"):
        spoken = " ".join(templates.render_readback({**FACTS, "kind": kind}))
        assert spoken.endswith("?"), kind  # one clear question, last (N1)
        assert spoken.count("?") == 1, kind
        if kind in ("RESCHEDULE", "CANCEL"):
            assert "HomeKeep Demo Service Desk" in spoken, kind  # N2
    cancel = " ".join(templates.render_readback({**FACTS, "kind": "CANCEL"})).casefold()
    assert "call off" in cancel
    assert "cancel" not in cancel  # "cancel" is a STOP command word (N1)
    reschedule = " ".join(templates.render_readback({**FACTS, "kind": "RESCHEDULE"}))
    assert "Flat 4, Example Residency, Pune" in reschedule  # N2


def test_review_outcome_wording() -> None:
    appointment = {"date_words": "Saturday, 17 October", "window_words": "10 am and 1 pm"}
    confirmed = " ".join(
        templates.render_outcome({"outcome": "CONFIRMED", "appointment": appointment})
    )
    assert "No real technician will visit." in confirmed  # N4: the exact disclosure
    storage = " ".join(
        templates.render_outcome({"outcome": "CONSENT_RECORDED", "purpose": "STORAGE"})
    )
    sharing = " ".join(
        templates.render_outcome({"outcome": "CONSENT_RECORDED", "purpose": "SHARING"})
    )
    assert "save" in storage
    assert "share" in sharing  # I9: says what was actually agreed
    assert "save" not in sharing
    not_sent = " ".join(templates.render_outcome({"outcome": "NOT_SENT"})).casefold()
    assert "nothing was sent" in not_sent  # I2
    _chunk_rules(templates.render_outcome({"outcome": "NOT_SENT"}))


def test_fr15_status_says_when_the_service_desk_last_updated_it() -> None:
    status = {
        "request": {"state": "SUBMISSION_PENDING"},
        "appointment": None,
        "last_update": "2026-10-16T09:35:00Z",  # 3:05 pm in Kolkata
    }
    spoken = " ".join(templates.render_status(status))
    assert "pending" in spoken
    assert "Friday, 16 October at 3:05 pm" in spoken  # FR-15-AC2
    _chunk_rules(templates.render_status(status))
