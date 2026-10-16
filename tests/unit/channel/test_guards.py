from __future__ import annotations

import pytest

from app.channel.guards import chunk_speech, command_for, hazard_in, output_guard

COMMANDS = [
    ("stop", "STOP"),
    ("Stop!", "STOP"),
    ("cancel", "STOP"),
    ("never mind", "STOP"),
    ("say that again", "REPEAT"),
    ("Repeat please", "REPEAT"),
    ("pardon?", "REPEAT"),
    ("slower", "SLOWER"),
    ("please speak slowly", "SLOWER"),
    ("slow down", "SLOWER"),
    ("pause", "PAUSE"),
    ("wait", "PAUSE"),
    ("hold on", "PAUSE"),
    ("talk to a person", "HUMAN"),
    ("I want to speak to a human", "HUMAN"),
    # Not commands: a command word inside a longer request is left to the agent.
    ("stop the AC from leaking", None),
    ("my AC won't stop beeping", None),
    ("hello", None),
]


@pytest.mark.parametrize(("utterance", "expected"), COMMANDS)
def test_fr21_command_grammar(utterance: str, expected: str | None) -> None:
    assert command_for(utterance) == expected


@pytest.mark.parametrize(
    ("utterance", "reason"),
    [
        ("I can see sparks", "SPARKS"),
        ("there's smoke", "SMOKE"),
        ("it keeps tripping", "REPEATED_TRIPPING"),
        ("the AC caught fire", "FIRE"),
        ("there are flames", "FIRE"),
        ("I got current when I touched it", "SHOCK"),
        ("current is coming from the AC", "SHOCK"),
        ("a burnt plastic smell", "BURNING_SMELL"),
        ("the MCB trips every time", "REPEATED_TRIPPING"),
        ("water near the switchboard", "WATER_NEAR_ELECTRICS"),
        ("it is not cooling", None),
        ("the remote is dead", None),
    ],
)
def test_fr07_hazard_guard_uses_the_lexicon(utterance: str, reason: str | None) -> None:
    hazard = hazard_in(utterance)
    assert (hazard.reason if hazard else None) == reason


@pytest.mark.parametrize(
    ("text", "blocked"),
    [
        ("Your demo technician is booked for Friday.", True),
        ("The appointment is confirmed.", True),
        ("I have scheduled a visit.", True),
        ("I've cancelled it for you.", True),
        ("A technician is coming tomorrow.", True),
        ("Open the front cover and clean the filter.", True),
        ("Check the refrigerant pressure.", True),
        ("Climb up and look at the vents.", True),
        ("Reset the breaker a few times.", True),
        ("The visit costs Rs 500.", True),
        ("A technician will visit you tomorrow morning.", True),
        ("I've arranged a technician for Friday.", True),
        ("The visit is set for 10 am tomorrow.", True),
        ("I've reserved a slot for you.", True),
        ("Your request has been placed.", True),
        ("Try climbing on a chair to look.", True),
        ("Touch the wires to check them.", True),
        ("It may need a gas refill.", True),
        ("That will cost five hundred rupees.", True),
        ("Please check the remote shows the snowflake sign.", False),
        ("Is the AC making a noise?", False),
    ],
)
def test_nfr06_output_guard(text: str, blocked: bool) -> None:
    result = output_guard(text)
    assert result.blocked is blocked, (text, result.violations)


def test_speech_is_chunked_to_two_sentences_and_one_question() -> None:
    chunks = chunk_speech("First. Second. Third? Fourth? Fifth.")
    for chunk in chunks:
        assert chunk.count("?") <= 1
        assert len([s for s in chunk.replace("?", ".").split(".") if s.strip()]) <= 2
    assert " ".join(chunks) == "First. Second. Third? Fourth? Fifth."
