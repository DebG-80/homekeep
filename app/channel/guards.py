"""Deterministic guards (TDD §4.3): command grammar, hazard lexicon and the output guard.

None of these call a model. The output guard is a regular-expression check: it blocks claims of
a booking or cancellation (there is no authoritative booking state until Slice 3), forbidden
repair instructions, and prices spoken without a stored fee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.catalog.hazards import match_hazard
from app.catalog.loader import Hazard

_COMMANDS: dict[str, tuple[str, ...]] = {
    "STOP": ("stop", "cancel", "never mind", "nevermind", "stop it", "stop talking", "no stop"),
    "REPEAT": (
        "repeat",
        "say that again",
        "say it again",
        "pardon",
        "what did you say",
        "come again",
        "repeat that",
    ),
    "SLOWER": ("slower", "speak slowly", "speak slower", "slow down", "more slowly", "talk slower"),
    "PAUSE": ("pause", "wait", "hold on", "one moment", "just a moment"),
    "HUMAN": (
        "talk to a person",
        "speak to a person",
        "speak to a human",
        "talk to a human",
        "real person",
        "human",
    ),
}
_FILLER = re.compile(
    r"\b(please|ok(ay)?|can you|could you|i want to|i'd like to|i would like to|just)\b"
)


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z' ]", " ", text.casefold())
    text = _FILLER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def command_for(utterance: str) -> str | None:
    """The command when the whole utterance is one (FR-21); a command word inside a longer
    request ("stop the AC from leaking") is left to the agent."""
    text = _normalise(utterance)
    for command, phrases in _COMMANDS.items():
        if text in phrases:
            return command
    return None


def hazard_in(utterance: str) -> Hazard | None:
    return match_hazard(utterance)


_CONFIRMATION = re.compile(
    r"\b(booked|book(ed)? (it|you|a visit)|confirmed|scheduled|cancel+ed|arranged|reserved"
    r"|appointment is (set|fixed)|(visit|appointment|slot) is (set|fixed|on)|(set|fixed) for"
    r"|request (has been |is )?(placed|raised|registered|submitted|sent)"
    r"|technician (is|will be) (coming|on (the|his|her|their) way|there)"
    r"|(technician|someone|engineer) (will|is going to) (visit|come|be there|call))\b",
    re.IGNORECASE,
)
_FORBIDDEN = re.compile(
    r"\b(refrigerant|capacitor|gas|(open|remove|unscrew|take off) (the )?(front )?(cover|panel|"
    r"casing|unit)|climb\w*|ladders?|stool|chair|screwdriver|wir(e|es|ing)|reset (the )?"
    r"(breaker|mcb|trip switch|fuse))\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = r"(one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand)"
_PRICE = re.compile(
    r"(₹|\brs\.?|\brupees?\b|\binr\b)\s*\d|\d+\s*(rupees?|rs\b)|\b"
    + _NUMBER_WORDS
    + r"\b[\w\s-]*\brupees?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardResult:
    text: str
    violations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def blocked(self) -> bool:
        return bool(self.violations)


def output_guard(text: str) -> GuardResult:
    violations = []
    if _CONFIRMATION.search(text):
        violations.append("UNBACKED_CONFIRMATION")
    if _FORBIDDEN.search(text):
        violations.append("FORBIDDEN_INSTRUCTION")
    if _PRICE.search(text):
        violations.append("PRICE_WITHOUT_FEE_STATE")
    return GuardResult(text, tuple(violations))


def chunk_speech(text: str) -> list[str]:
    """Split into chunks of at most two sentences and one question, keeping every word."""
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        questions = sum(s.count("?") for s in current) + sentence.count("?")
        if current and (len(current) == 2 or questions > 1):
            chunks.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks
