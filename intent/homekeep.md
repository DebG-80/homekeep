# Intent: HomeKeep — voice-first appliance care for elders

Author: Deb (product owner). Status: accepted. Date: 2026-10-01.
Detailed requirements: `docs/HomeKeep_BRD_v1.0.md`. Design: `docs/HomeKeep_TDD_H_v1.0.md`.

## Problem
Elders in Indian households know when an appliance stops working, but often lack the model number, invoice or purchase date. They also lack a dependable way to organise a repair. Booking apps, repeated explanations and lost service records turn a simple fault into a burden.

## Proposed outcome
An elder says what is wrong, in their own words, by voice. HomeKeep remembers the appliance and the case across conversations. It offers only evidence-backed checks, books a (demo) technician after explicit spoken approval, and closes the case only when the elder confirms the problem is fixed.

## Affected users and systems
- Elders: primary voice users after assisted setup
- Helpers or family: optional, with scoped grants
- Service coordinators and technicians: staff console
- Judges: hosted demo and the MCP endpoint
- Systems: browser voice client, HomeKeep MCP server, Amazon Bedrock, DynamoDB, S3, Cognito

## Constraints
- No paperwork prerequisite; every appliance field except category and nickname may stay unknown.
- Booking and provider are simulated in H and must be disclosed as demo.
- The model never approves or executes a consequential action; deterministic code does.
- Hackathon rules: an MCP server on spec 2025-11-25 over Streamable HTTP, a public repo with an OSI licence, a demo under 3 minutes, submission by 23 Oct 2026 12:00 PDT.
- English only in H; at most 3 concurrent users.

## Open questions (tracked in BRD §15.3)
- D04: Alexa+ production access and India availability (P launch gate)
- D05: Hindi, Hinglish and regional-language priorities (P)
- D07, D08: retention, consent and real provider operations (P)
