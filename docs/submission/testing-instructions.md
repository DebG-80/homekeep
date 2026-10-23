# Testing instructions (template)

**Credentials are entered only in the Devpost field. Never paste them here.** This file is public. It holds the wording for the Devpost "Testing instructions" field with `<PLACEHOLDERS>`; replace them only inside Devpost.

Deb: check every step against the hosted demo before pasting, and adjust any phrase that does not work there.

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
4. Chrome uses its own microphone choice, not always the one macOS or Windows is using. With a headset, open Chrome **Settings → Privacy and security → Site settings → Microphone** and pick the headset from the list; otherwise Chrome may listen to the built-in microphone and hear nothing.
5. After you press **Start talking**, just speak and then pause: HomeKeep sends what you said by itself after about a second. **Esc is Stop**: it cancels the current turn, so don't press it to send.

## Try it by voice

Sign in with your household login and open **Talk**. Press **Start talking** (or the Space bar) and speak normally; wait for HomeKeep to finish before you answer. You can say **"stop"**, **"repeat that"** or **"slower"** at any time.

1. **Say hello:** *"Hi."* HomeKeep says what it helps with. Your household already allows HomeKeep to save your appliances, as if a family member set it up for you.
2. **Add an appliance:** *"I have an AC in the bedroom."* If HomeKeep asks what you call it, give a name such as *"Bedroom AC"*; it is saved straight away.
3. **Report a problem:** *"It isn't cooling."* Answer its questions one at a time; *"I'm not sure"* is always accepted.
4. **Hear a safety warning (optional):** *"Now it smells like something is burning."* HomeKeep gives approved safety advice and stops routine checks.
5. **Ask for a technician:** *"Please send someone."* When asked, give a made-up address and phone number, then choose a time such as *"tomorrow morning"*.
6. **Approve the booking:** HomeKeep reads back the provider, the full date and time window, the fee (an estimate), the address, what is shared, and that this is a demonstration. When it has finished and asks *"Shall I book it?"*, say *"yes"*. You hear *"Your demo booking is confirmed for … This is a demonstration. No real technician will visit."*
7. **Come back later:** reload the page and ask *"Is my visit booked?"* HomeKeep remembers the case.
8. **After the visit:** sign in as the technician, open the case under **Service desk** and press **Visit completed** with a short note. Back in your household, say *"It works now, you can close it."* Only your answer closes the problem; the technician's report alone does not.
9. **See the history:** open **Household and history** and choose **History** next to the appliance.

## Try it by text

Every step above also works by typing into the box under the conversation and pressing Enter. This is useful if you have no microphone. A typed "yes" approves the booking for usability, but it is recorded as a text approval, never as a voice one.

## Check the MCP server with MCP Inspector

1. Run MCP Inspector locally (`npx @modelcontextprotocol/inspector@<INSPECTOR_VERSION>`). TODO(Deb): replace with the version you tested against the hosted demo.
2. Connect with transport **Streamable HTTP** to `<APP_URL>/mcp`.
3. Inspector discovers the authorisation server from the Protected Resource Metadata at `<APP_URL>/.well-known/oauth-protected-resource`.
4. Use the pre-registered public client: Client ID `<MCP_INSPECTOR_CLIENT_ID>`, no secret, PKCE; the redirect URL is Inspector's default local callback. Sign in with your household login.
5. Expected: the handshake reports protocol version `2025-11-25`. The tool list shows the customer tools and also the three trusted tools (`confirm_action`, `execute_action`, `cancel_pending_action`), which refuse any call without HomeKeep's channel attestation (step 6).
   Known limit: Inspector does not send HomeKeep's `X-HK-Turn-Id` header, so the server gives each of its calls a fresh turn ID. Tools work, but a retried call from Inspector is not de-duplicated the way HomeKeep's own voice channel is.
6. Expected refusal: calling a trusted tool such as `confirm_action` from Inspector is refused with `AUTH_DENIED`. Only HomeKeep's own channel, after a spoken "yes", can approve a booking.

## Reset your demo data

Open **Household and history** and press **Reset my demo data** at the bottom (owner logins of the judge households only). It removes everything you added (appliances, problems, bookings and history) and puts your household back to its starting state. Your login keeps working, and you can start again at step 1.

## Known limits

- All bookings are a **demonstration**. No real technician will visit.
- English only. Chrome desktop only for voice.
- Guidance exists only for the fictional "Frostline FL-18i" air conditioner; other appliances get general questions and a service request.
- TODO(Deb): add limits found during testing.
