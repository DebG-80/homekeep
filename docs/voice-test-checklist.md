# Voice acceptance checklist (Deb)

The automated suite types instead of speaking. Seeded transcripts and stubbed speech never count as a voice pass (BRD §12.1, FR-21-AC2). These runs are the voice evidence for AT-13 (voice parts), AT-22 and AT-23 (TDD §12.1). Record each run on video; the AT-22 recording becomes the core of the demo video.

## Setup

- Chrome desktop, current stable, on the deployed app (or `make run` for a rehearsal).
- A headset, so HomeKeep doesn't hear itself. Select it in Chrome **Settings → Privacy and security → Site settings → Microphone**: Chrome keeps its own microphone choice, and without this it listened to the wrong input and heard nothing (23 Oct run).
- Speak, then pause: the phrase is sent after about a second of silence. **Esc is Stop** and cancels the turn; never press it to send.
- Sign in as a judge household, then use **Reset my demo data** so the run starts clean.
- After sign-in and the first microphone click, hide the screen or turn the monitor off. An observer fills in the table below.
- Timing: a phone stopwatch, or a screen recording with an audible click track.

## AT-22: the whole journey by speech only (screen hidden)

| # | Say | Expect to hear | Pass? |
| --- | --- | --- | --- |
| 1 | "Please remember my appliances", then "yes" | The consent question; then "Thank you. I'll save your appliances…" | |
| 2 | "I have an AC in the bedroom" | It is saved, and HomeKeep asks what is wrong | |
| 3 | "It isn't cooling" | The problem is noted; one question at a time | |
| 4 | "Send a technician" | It asks for an address, then a phone number | |
| 5 | Give an address and a number | Thanks; it offers times | |
| 6 | Choose "tomorrow morning" | The read-back: provider, full date, window, fee "estimated" or "not known", warranty not known, address, what is shared, "This is a demonstration. No real technician will visit.", "Shall I book it?" | |
| 7 | "yes" (after the read-back has finished) | "Your demo booking is confirmed for …" with the date in words | |
| 8 | Reload the page, then "Is my visit booked?" | The same confirmed visit (resume) | |
| 9 | "Can we move it to the afternoon?", then "yes" after the read-back | The change read-back, then "Your demo visit is moved to …" | |
| 10 | (Technician marks the visit completed in the service desk) "Is it fixed?" / "It works now, close it" | It asks whether it works, then "I've closed this problem." | |

## AT-13 (voice): what must not count as "yes"

| # | Do | Expect | Pass? |
| --- | --- | --- | --- |
| 1 | Stay silent for 40 s after a read-back | A reprompt at about 15 s, then "I'll pause here. Your progress is saved." Nothing is booked | |
| 2 | Play a recording of someone saying "yes" nearby while HomeKeep is reading back | Nothing is booked | |
| 3 | Say "yes" *during* the read-back | Nothing is booked | |
| 4 | Wait more than 5 minutes after a read-back, then say "yes" | "That confirmation has timed out…" | |
| 5 | "Saturday… no, Sunday" | A new read-back with Sunday; only a fresh "yes" books it | |
| 6 | A clear "yes" after the read-back finishes | Booked once | |

## AT-23: microphone denied and connection lost

| # | Do | Expect | Pass? |
| --- | --- | --- | --- |
| 1 | Block the microphone in Chrome's site settings, then press Start talking | "I need the microphone to hear you. You can type instead." The page says voice is blocked and text is not a voice pass | |
| 2 | DevTools → Network → Offline, then say something | "I lost the connection. I'll check what was saved." No claim that anything was saved | |
| 3 | Go back online | The same request is retried once; the reply arrives | |

## Timing (NFR-01, FR-21)

| Measure | Target | Measured |
| --- | --- | --- |
| "Stop" while HomeKeep is speaking: until speech stops | Within 1 s | |
| End of your speech to the start of HomeKeep's reply (typical) | About 4 s; "One moment, I'm still working on that" if longer | |

## Observer sign-off

| Run | Date | Observer | Video link | Result |
| --- | --- | --- | --- | --- |
| AT-22 | | | | |
| AT-13 voice | | | | |
| AT-23 | | | | |
