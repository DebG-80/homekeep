# Devpost project story (draft)

Paste each section into the matching Devpost field near submission. Facts below come from the TDD, BRD and HANDOFF. Anything not yet built is marked `TODO`. **Do not claim a feature works until its slice has passed verification and you have seen it on the hosted demo.**

Required disclosures, keep them in the final text:
- **Demo service desk.** Every booking is simulated; no real technician is dispatched. HomeKeep says "No real technician will visit" whenever it confirms a demo booking.
- **Fictional brand.** "Frostline" (models FL-18i and FL-24x) is a fictional appliance brand with a manual written from scratch for this project. No real manufacturer content is used.

## Inspiration

Elders in Indian households usually know when an appliance stops working, but often don't have the model number, the invoice or the purchase date. Booking apps, repeated explanations and lost service records turn a simple fault into a burden. We wanted a helper they could simply talk to.

TODO(Deb): a short personal line on why this matters to you.

## What it does

HomeKeep lets an elder report an appliance problem by voice, in their own words, with no paperwork. It keeps each appliance case alive across conversations, from the spoken problem to a fix the elder confirms.

- Remembers appliances and open cases between conversations; nothing but the appliance type and a nickname is ever required.
- Offers checks only when they are backed by a reviewed manual for the exact, verified model. Otherwise it says it has no approved guidance and offers service.
- Stops and gives approved safety advice on warning signs such as a burning smell or sparks.
- Reads a booking back in full (provider, full date, time window, fee or fee uncertainty, demo status) and books a **demo** technician only after the elder says "yes" at the right moment. The decision is made by deterministic code, never by the language model.
- Closes a case only when the elder confirms the problem is fixed; a technician marking a visit complete is not enough.

TODO(slice-4): confirm each bullet against the hosted demo before submission and delete any that is not demonstrable.

## How we built it

- **Alexa+ track:** a self-hosted MCP server (`/mcp`, spec `2025-11-25`, Streamable HTTP, stateless, OAuth via Amazon Cognito) built with the MCP Python SDK 1.29.1. HomeKeep's own agent calls its tools only through an MCP client over HTTP, so the MCP path is exercised on every turn. TODO(slice-2): link the code path `app/orchestrator/agent.py`.
- **Conversation:** the Strands Agents SDK with Claude Haiku 4.5 on Amazon Bedrock (Converse API). The agent sees only customer tools; approval and execution tools are reachable only by the channel's deterministic approval guard.
- **Data:** one Amazon DynamoDB table with optimistic versions, conditional writes and transactions; documents in a private Amazon S3 bucket with a quarantine-then-validate flow.
- **Hosting:** one ARM64 container on Amazon ECS Express Mode (Fargate behind an Application Load Balancer with an AWS-provided HTTPS domain), images in Amazon ECR, logs in CloudWatch, costs watched by AWS Budgets.
- **Voice client:** TypeScript and Vite, using the browser's Web Speech API with the `en-IN` locale; the browser voice client is the simulated Alexa+ experience on top of the MCP server.
- **Process:** an AI-native SDLC with Claude Code: an approved plan per slice, tests first, an independent verifier and a policy reviewer before each merge (`docs/SDLC.md`).

## Challenges we ran into

- AWS App Runner was closed to new customers, which forced a hosting change to ECS Express Mode (friction log FL-01).
- TODO(Deb): add the real challenges as they happen; link friction-log entries.

## Accomplishments that we're proud of

TODO(Deb): fill after the demo works. Candidates, only if demonstrated: integrity rules enforced in code rather than prompts; spoken outcomes always from server templates; the full case lifecycle surviving a restart.

## What we learned

TODO(Deb).

## What's next for HomeKeep

- A production Alexa+ adapter replacing the browser channel (the domain and MCP layers stay as they are).
- Hindi, Hinglish and regional languages.
- Real service-provider integration, once retention, consent and provider operations are settled (BRD D07, D08).
- MCP SDK 2.x and spec 2026-07-28 once the event confirms later versions.
