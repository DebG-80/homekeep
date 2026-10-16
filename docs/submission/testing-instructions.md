# Testing instructions (template)

**Credentials are entered only in the Devpost field. Never paste them here.** This file is public. It holds the wording for the Devpost "Testing instructions" field with `<PLACEHOLDERS>`; replace them only inside Devpost.

TODO(slice-4): complete once the hosted demo, the seed script and the reset action exist. Check every step against the hosted demo before pasting.

---

## Where to test

- App: `<APP_URL>`
- MCP endpoint: `<APP_URL>/mcp`
- Available free of charge until **20 November 2026**.

## Accounts

Each judge gets a separate demo household, so judges do not affect each other. Use the login for your household from the list in this Devpost field:

| Household | Login |
| --- | --- |
| J1 | Username: `<J1_USERNAME>` / Password: `<J1_PASSWORD>` |
| J2 | Username: `<J2_USERNAME>` / Password: `<J2_PASSWORD>` |
| J3 | Username: `<J3_USERNAME>` / Password: `<J3_PASSWORD>` |
| Staff (coordinator) | Username: `<COORDINATOR_USERNAME>` / Password: `<COORDINATOR_PASSWORD>` |
| Staff (technician) | Username: `<TECHNICIAN_USERNAME>` / Password: `<TECHNICIAN_PASSWORD>` |

## Browser setup

1. Use **Chrome on a desktop or laptop**, current version. A headset gives the best voice results.
2. Set Chrome's language list to include **English (India)**. HomeKeep listens with the `en-IN` locale.
3. Allow the microphone when Chrome asks. If you decline, HomeKeep switches to typing.

## Try it by voice

TODO(slice-4): the step-by-step journey (register an appliance, report a problem, answer questions, hear a safety warning, book a demo visit after the read-back, then confirm the fix), with the exact phrases that work well.

## Try it by text

TODO(slice-4): the same journey using the text box, for judges without a microphone. Note that a typed "yes" counts for usability but is not treated as a voice approval.

## Check the MCP server with MCP Inspector

1. Run MCP Inspector locally (`npx @modelcontextprotocol/inspector`). TODO(slice-2): pin the Inspector version that was tested.
2. Connect with transport **Streamable HTTP** to `<APP_URL>/mcp`.
3. Inspector discovers the authorisation server from the Protected Resource Metadata at `<APP_URL>/.well-known/oauth-protected-resource`.
4. Use the pre-registered public client: Client ID `<MCP_INSPECTOR_CLIENT_ID>`, no secret, PKCE; the redirect URL is Inspector's default local callback. Sign in with your household login.
5. Expected: the handshake reports protocol version `2025-11-25`, and the tool list shows the customer tools.
   Known limit: Inspector does not send HomeKeep's `X-HK-Turn-Id` header, so the server gives each of its calls a fresh turn ID. Tools work, but a retried call from Inspector is not de-duplicated the way HomeKeep's own voice channel is.
6. Expected refusal: calling a trusted tool such as `confirm_action` from Inspector is refused with `AUTH_DENIED`. Only HomeKeep's own channel, after a spoken "yes", can approve a booking.

## Reset your demo data

TODO(slice-4): where the "Reset my demo data" control is, and what it restores.

## Known limits

- All bookings are a **demonstration**. No real technician will visit.
- English only. Chrome desktop only for voice.
- Guidance exists only for the fictional "Frostline FL-18i" air conditioner; other appliances get general questions and a service request.
- TODO(Deb): add limits found during testing.
