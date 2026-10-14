---
name: elder-voice-copy
description: HomeKeep's rules for anything the elder hears or reads. Use whenever writing or changing response templates, system prompts, read-backs, hazard or escalation text, demo disclosures, error messages shown to customers, or tests that assert on spoken output.
---

# Elder voice copy

Source: BRD §5.1–5.5, FR-12, FR-21, FR-27; TDD §4.3 and §8.3.

## Every spoken reply
- At most **two sentences and one question**. Lead with the action or the question; offer more detail only on request.
- Plain words: no jargon, model codes, IDs or URLs. Say "your bedroom AC", not an appliance ID.
- Accept "not sure" or "I don't know" without re-asking. Never invent a value.
- Never speak a full address, phone number or other personal detail unless the action needs it and the actor is authorised.

## Outcomes come from server templates only
- Booking, reschedule and cancellation outcomes, approval read-backs, hazard escalations and consent text live in `app/channel/templates.py` (or the file the plan names). The LLM never phrases them.
- Confirmed: say "demo booking confirmed", the full date in words (Asia/Kolkata), the time window and the provider, then "This is a demonstration; no real technician will visit."
- Pending or unknown: say "pending"; never "booked" or "confirmed".
- Fees: say the amount and whether it is an estimate. Unknown is spoken as "the fee is not known yet". **Unknown is never "free".**
- Warranty or coverage: "not known" unless provider-confirmed.

## Read-backs before approval (FR-12)
Must cover action, provider, full date and window, fee or fee uncertainty, address confirmation, data shared, and demo status. End with one clear question: "Shall I book it?" Split long read-backs into short parts, but never drop a material item.

## Safety (FR-07)
- Hazard replies use the approved text from `catalog_data/hazards.json`, verbatim.
- Never tell anyone to climb, open or remove covers, touch wiring, handle refrigerant, or repeatedly reset a tripping unit.
- Never claim emergency dispatch.

## Tests
Assert on template keys plus required fragments ("demo", "No real technician will visit", the explicit date). Don't assert on whole free-text model replies.
