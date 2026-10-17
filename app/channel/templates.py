"""Every sentence the server speaks on its own authority (CLAUDE.md invariant 6).

Hazard escalations come verbatim from catalog_data/hazards.json and guidance steps verbatim from
the catalog; the strings here cover commands, guards, caps and errors. Rules: elder-voice-copy
(at most two sentences and one question, plain words, never "booked" without an authoritative
result, any technician mention says "demo").
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from app.domain.clock import DEFAULT_TIMEZONE
from app.domain.requests import as_utc, date_words
from app.provider.simulator import PROVIDER_NAME

COMMANDS: dict[str, str] = {
    "STOP": "Okay, I've stopped. Nothing new was saved or sent.",
    "SLOWER": "Of course. I'll speak more slowly.",
    "PAUSE": "Okay, I'll wait. Your progress is saved.",
    "HUMAN": "I can help you arrange a demo technician visit. Shall we do that?",
}
NOTHING_TO_REPEAT = "I haven't said anything yet. How can I help with your appliances?"
OUTPUT_GUARD_FALLBACK = (
    "I need to check that properly before I say more. What would you like to do next?"
)
CYCLE_CAP = (
    "I'm having trouble with that just now. I can help you arrange a demo technician visit instead."
)
DAILY_CAP = "We've talked a lot today, so let's continue tomorrow. Everything so far is saved."
TURN_ERROR = "Something went wrong on my side. Please say that again."
GUIDANCE_FOLLOW_UP = "Tell me how it goes."
DEMO_DISCLOSURE = "This is a demonstration. No real technician will visit."
STILL_WORKING = "I'm still working on that. One moment, please."

STILL_PENDING = "Your request is still pending. I'll tell you as soon as I hear back."

APPROVAL_EXPIRED = (
    "That confirmation has timed out, so nothing was sent. Shall I read it to you again?"
)
APPROVAL_DECLINED = "Okay, I won't go ahead. Nothing has been sent."
APPROVAL_REFUSED = "Something changed, so I didn't go ahead. Shall I read the details again?"

# --- read-backs (FR-12: every material item, ending with one clear question) ---------------

_DISCLOSURE = DEMO_DISCLOSURE  # the exact wording (TDD §4.6)


def moment_words(instant: str) -> str:
    """A stored UTC instant as spoken in Asia/Kolkata: "Friday, 16 October at 3:05 pm"."""
    local = as_utc(instant).astimezone(ZoneInfo(DEFAULT_TIMEZONE))
    hour = local.hour % 12 or 12
    clock = f"{hour}:{local.minute:02d}" if local.minute else str(hour)
    suffix = "am" if local.hour < 12 else "pm"
    return f"{date_words(local.date().isoformat())} at {clock} {suffix}"


def fee_sentence(fee_paise: int | None) -> str:
    if not fee_paise:
        return "The fee is not known yet."  # unknown is never spoken as free (FR-27)
    return f"The fee is an estimated {fee_paise // 100} rupees."


def render_readback(facts: dict[str, Any]) -> list[str]:
    from app.channel.guards import chunk_speech

    kind = facts["kind"]
    # One clear question, always last. "Call off", not "cancel": "cancel" is a STOP command
    # word, so an elder repeating it would drop the request instead of answering (N1).
    if kind == "CONSENT_STORAGE":
        text = (
            "You can ask me to stop at any time. May I save your appliances and the problems you "
            "tell me about, so I can help you next time?"
        )
    elif kind == "CONSENT_SHARING":
        text = (
            "You can change this later. May I share updates about your appliances with the "
            "family members you have chosen?"
        )
    elif kind == "CANCEL":
        text = (
            f"Your appliance problem stays open. Shall I call off the demo visit from "
            f"{facts['provider']} on {facts['date_words']}, between {facts['window_words']}?"
        )
    elif kind == "RESCHEDULE":
        text = (
            f"Here is the change to check. Your demo visit from {facts['provider']} would move "
            f"to {facts['date_words']}, between {facts['window_words']}, at {facts['address']}. "
            f"Your current time stays in place until the change goes through. "
            f"{fee_sentence(facts.get('fee_paise'))} HomeKeep would share the same details as "
            f"before. {_DISCLOSURE} Shall I change it?"
        )
    else:
        text = (
            f"Here is the booking to check. A demo visit from {facts['provider']} on "
            f"{facts['date_words']}, between {facts['window_words']}. "
            f"{fee_sentence(facts.get('fee_paise'))} The warranty is not known. "
            f"The technician would come to {facts['address']}. "
            f"HomeKeep would share your appliance problem and your contact, {facts['contact']}. "
            f"{_DISCLOSURE} Shall I book it?"
        )
    return chunk_speech(text)


# --- outcomes (spoken only from the server's authoritative result; invariant 6) -------------

OUTCOMES: dict[str, str] = {
    "CONFIRMED": (
        "Your demo booking is confirmed for {date}, between {window}, with {provider}. "
        + _DISCLOSURE
    ),
    "PENDING": (
        "I've sent the request, and it is pending. I'll check again and tell you what I hear."
    ),
    "REQUESTED": "The service desk has the request, but no time is fixed yet, so it is pending.",
    "REJECTED": "The service desk couldn't take that request. Shall I find another time?",
    "FAILED": "The booking didn't go through. Shall I try again?",
    "SLOT_UNAVAILABLE": "That time has just been taken. Shall I find another one?",
    "FEE_CHANGED": (
        "The fee has changed to an estimated {rupees} rupees. Shall I read the details again?"
    ),
    "CHANGED": "Your demo visit is moved to {date}, between {window}. " + _DISCLOSURE,
    "CHANGE_FAILED": "I couldn't move it, so your visit stays on {date}, between {window}.",
    "CANCEL_PENDING": (
        "I've asked to cancel it, and that is pending. The visit stands until I hear back."
    ),
    "CANCELLED": "Your demo visit is called off. Your appliance problem is still open.",
    "CANCEL_REFUSED": (
        "The service desk couldn't call it off, so your visit stays on {date}, between {window}."
    ),
    "CONSENT_RECORDED": "Thank you. I'll save your appliances and problems from now on.",
    "CONSENT_SHARING_RECORDED": (
        "Thank you. I'll share updates with the family members you have chosen."
    ),
    "NOT_SENT": "That didn't go through, and nothing was sent. Shall I try again?",
}


def render_outcome(result: dict[str, Any]) -> list[str]:
    from app.channel.guards import chunk_speech

    appointment = result.get("appointment") or {}
    outcome = result["outcome"]
    if outcome == "CONSENT_RECORDED" and result.get("purpose") == "SHARING":
        outcome = "CONSENT_SHARING_RECORDED"  # say what was actually agreed (I9)
    template = OUTCOMES.get(outcome, TURN_ERROR)
    return chunk_speech(
        template.format(
            date=appointment.get("date_words", "the agreed day"),
            window=appointment.get("window_words", "the agreed time"),
            provider=PROVIDER_NAME,
            rupees=(result.get("fee_paise") or 0) // 100,
        )
    )


def render_status(status: dict[str, Any]) -> list[str]:
    from app.channel.guards import chunk_speech

    state = status["request"]["state"]
    appointment = status.get("appointment") or {}
    if state in ("CONFIRMED", "IN_PROGRESS"):
        text = (
            f"Your demo visit is on {appointment.get('date_words')}, between "
            f"{appointment.get('window_words')}, with {PROVIDER_NAME}."
        )
    elif state in ("SUBMISSION_PENDING", "CHANGE_PENDING", "CANCEL_PENDING", "REQUESTED"):
        text = STILL_PENDING
        if status.get("last_update"):  # FR-15-AC2: when it was last updated
            text += f" It was last updated on {moment_words(status['last_update'])}."
    elif state == "COMPLETED":
        text = "The technician has marked the visit as done. Is the problem fixed now?"
    elif state == "CANCELLED":
        text = "That demo visit was called off. Your appliance problem is still open."
    elif state in ("REJECTED", "FAILED"):
        text = "That request didn't go through. Shall I try again?"
    else:
        text = "Your request isn't sent yet. Shall we finish it?"
    return chunk_speech(text)


_RESOLUTION = {
    "RESOLVED": "I'm glad it's working. I've noted that the problem is fixed.",
    "PERSISTS": "I'm sorry it's still not right. I've noted it, and we can arrange another visit.",
    "UNSURE": "That's alright. Tell me later whether it's working, and I'll note it then.",
}
_UNCANCELLED_VISIT = "A demo visit is still booked. Shall I call it off?"

# Spoken words for each history event; anything not listed is left out of the spoken summary
# (it stays in the record).
_HISTORY_WORDS = {
    "APPLIANCE_REGISTERED": "it was added",
    "ISSUE_REPORTED": "a problem was reported",
    "ISSUE_RECURRED": "the problem came back",
    "SERVICE_CONFIRMED": "a demo visit was booked",
    "SERVICE_RESCHEDULED": "the demo visit was moved",
    "SERVICE_CANCELLED": "the demo visit was called off",
    "STAFF_VISIT_COMPLETED": "the technician marked the visit as done",
    "ISSUE_CUSTOMER_SAYS_PERSISTS": "the household said the problem was still there",
    "ISSUE_CUSTOMER_CONFIRMED_RESOLVED": "the household said it was fixed",
    "ISSUE_CUSTOMER_CLOSED": "the problem was closed",
}
HISTORY_SPOKEN_ENTRIES = 3


def render_resolution(result: dict[str, Any]) -> list[str]:
    """The reply to the customer's own answer (FR-17). A visit still booked is mentioned, never
    cancelled silently."""
    from app.channel.guards import chunk_speech

    text = _RESOLUTION.get(result["answer"], TURN_ERROR)
    if result["answer"] == "RESOLVED" and result.get("closed"):
        text = "I'm glad it's working. I've closed this problem."
    chunks = chunk_speech(text)
    if result.get("uncancelled_visit") and result["answer"] == "RESOLVED":
        chunks.append(_UNCANCELLED_VISIT)
    return chunks


def render_history(history: dict[str, Any]) -> list[str]:
    """The latest few attributed events, oldest first, each with its date in words (FR-18)."""
    spoken = [e for e in history["entries"] if e["action"] in _HISTORY_WORDS]
    if not spoken:
        return [f"I have nothing recorded yet for your {history['appliance']}."]
    latest = spoken[-HISTORY_SPOKEN_ENTRIES:]
    chunks = [f"Here is the latest for your {history['appliance']}."]
    chunks += [f"On {e['date_words']}, {_HISTORY_WORDS[e['action']]}." for e in latest]
    return chunks
