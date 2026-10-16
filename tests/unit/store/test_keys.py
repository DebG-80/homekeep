from __future__ import annotations

from app.store import keys


def test_keys_match_tdd_6_1_layout() -> None:
    assert keys.household_pk("h1") == "HH#h1"
    assert keys.META == "META"
    assert keys.member_sk("s1") == "MEMBER#s1"
    assert keys.user_pk("s1") == "USER#s1"
    assert keys.user_household_sk("h1") == "HH#h1"
    assert keys.consent_sk("STORAGE", "2026-10-16T00:00:00.000000Z", "r1") == (
        "CONSENT#STORAGE#2026-10-16T00:00:00.000000Z#r1"
    )
    assert keys.appliance_sk("a1") == "APPL#a1"
    assert keys.nickname_sk("bedroom ac") == "NICK#bedroom ac"
    assert keys.issue_sk("i1") == "ISSUE#i1"
    assert keys.observation_sk("i1", "onset") == "ISSUE#i1#OBS#onset"
    assert keys.observation_prefix("i1") == "ISSUE#i1#OBS#"
    assert keys.operation_sk("abc") == "OP#abc"
    assert keys.event_sk("a1", "t", "e1") == "EVT#a1#t#e1"
    assert keys.event_sk(None, "t", "e1") == "EVT#-#t#e1"
    assert keys.event_prefix("a1") == "EVT#a1#"
