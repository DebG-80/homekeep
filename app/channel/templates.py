"""Every sentence the server speaks on its own authority (CLAUDE.md invariant 6).

Hazard escalations come verbatim from catalog_data/hazards.json and guidance steps verbatim from
the catalog; the strings here cover commands, guards, caps and errors. Rules: elder-voice-copy
(at most two sentences and one question, plain words, never "booked" without an authoritative
result, any technician mention says "demo").
"""

from __future__ import annotations

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
