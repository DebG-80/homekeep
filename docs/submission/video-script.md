# Demo video script (draft, under 3:00)

Constraints:
- Total running time **under 3 minutes**; aim for 2:50 to leave a margin.
- No copyrighted music. No real brands, products or people on screen or in narration; the appliance is the fictional "Frostline FL-18i".
- Captions on for the whole video.
- Record the voice journey with the screen hidden from the speaker after assisted launch (AT-22), on Chrome desktop with a headset.
- HomeKeep's spoken lines in the video come from server templates (`app/channel/templates.py`, `catalog_data/hazards.json`); never write new HomeKeep lines into this script. The lines you will hear, verbatim:
  - Burning smell: *"Please stop using it and switch it off if you can do that safely, then keep away from it. I'll help you get a demo technician to check it."*
  - Read-back: ends *"This is a demonstration. No real technician will visit. Shall I book it?"*
  - Confirmation: *"Your demo booking is confirmed for {date}, between {window}, with HomeKeep Demo Service Desk. This is a demonstration. No real technician will visit."*
  - After the elder says it works and asks to close: *"I'm glad it's working. I've closed this problem."*

| Time | Screen | Narration (presenter, not HomeKeep) | Rule or AT proved |
| --- | --- | --- | --- |
| 0:00–0:15 | Title, then an elder beside a silent AC | The problem: no model number, no invoice, no app; just "the bedroom AC isn't cooling". | Problem statement |
| 0:15–1:00 | Voice journey: register the AC by nickname, report the problem, answer two questions with "not sure" accepted | HomeKeep remembers the appliance and the case; nothing beyond a type and a nickname is required. | AT-22 (speech only, screen hidden) |
| 1:00–1:15 | The elder mentions a burning smell | Warning signs get approved safety advice, and routine checks stop. | AT-08, FR-07 |
| 1:15–1:45 | Read-back of the demo booking, then the elder says "yes" | The model can only propose. Deterministic code approves after a complete read-back and a clear spoken "yes"; the confirmation says it is a demo. | AT-13, FR-12, invariant 2 |
| 1:45–2:10 | Staff console marks the visit complete; the elder's next session asks if it's fixed | A technician can't close the case; only the elder's answer does. | AT-19, invariant 8 |
| 2:10–2:35 | MCP Inspector: handshake shows `2025-11-25`, tool list, then a refused `confirm_action` | A real MCP server on spec 2025-11-25 over Streamable HTTP, called at runtime by HomeKeep itself; external clients can't approve actions. | Alexa+ track eligibility; AT-10 |
| 2:35–2:55 | Architecture diagram (`docs/architecture/homekeep_aws_architecture.png`) | One container on ECS Express Mode with Bedrock, Strands, DynamoDB and Cognito. | AWS Builder mini challenge |

TODO(Deb): rehearse with a timer; cut words, not beats. Upload to YouTube or Vimeo (public or unlisted) and paste the link in Devpost.
