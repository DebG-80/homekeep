# What Claude needs from Deb (after Slice 4)

17 Oct 2026. Deadline 23 Oct, 12:00 PDT.

This page lists only the open items that **need your input**: a decision, a result from AWS or a voice run, or content only you can write. Everything else left is being fixed without you; it is listed at the end so you know it is in hand.

Reply with the item number and your answer, for example "1a, 2: keep all deferred, 5: done, works". The section "Your own work: where it is listed" points to your other checklists.

## Decide now (these block the first deploy or change what gets built)

### 1. `BUCKET_NAME`: done (1a, 21 Oct)
You chose 1a. `BUCKET_NAME` is removed from the app, and infra-contract §4 now says not to create a bucket. The §6.1 task role has no S3 statements. Skip §4; don't set `BUCKET_NAME`.

### 2. The deferred items (P1-1): build any of them before the deadline?
Still deferred:
- FR-19 reminders;
- FR-04 documents and S3;
- the Ops page;
- the formal AT-29 load run;
- `evals.yml`;
- `smoke.yml`.

**Recommendation:** keep them all deferred, except possibly `smoke.yml`. That would be a daily check of `/healthz` and the MCP endpoint's 401 with metadata. It needs no secrets, and it feeds SDLC stage 6.

**If you want any built, Claude needs these from you:**
- **`evals.yml`:** a GitHub OIDC role in AWS that can call Bedrock, and its ARN as a repository variable. You provision the role; Claude writes the workflow.
- **`smoke.yml`:** the deployed app URL as a repository variable. A full text turn would also need a judge login stored as a GitHub secret, which I'd skip.
- **Any of the others:** say which, and Claude writes a short plan addendum first. Each costs roughly a day.

### 3. Open Source mini challenge (optional)
A public main repo doesn't qualify on its own (HANDOFF §3). A candidate is extracting the demo provider simulator, or the attested-approval MCP pattern, as its own small licensed package.

**Your answer:** yes (which one), or no. **Recommendation:** no, given the deadline. A project can win only one mini-challenge prize anyway.

### 4. `docs/HANDOFF.md`: done (21 Oct)
You said yes. Row 12 now records that `TransactWriteItems` was dropped (D-3), and decision 20 records that the bucket was removed.

## Needs results from your AWS work (send them when you have them)

### 5. Bedrock model access: form needed (23 Oct)
Your own `converse` call from the CLI worked, but the app's first turn on ECS failed with `ResourceNotFoundException`. CloudTrail showed: "Model use case details have not been submitted for this account. Fill out the Anthropic use case details form before using the model." You submitted the form through **Bedrock → Model catalog → Claude Haiku 4.5**. So **a successful test call does not prove the account is cleared**. The profile's destination regions (`us-east-1`, `us-east-2`, `us-west-2`) match infra-contract §6.1. This is worth a friction-log entry: the check passed for one caller and failed for the app's role, and the app saw only a generic error.

### 6. MCP Inspector against the hosted `/mcp`
**What to do:** follow `docs/submission/testing-instructions.md`, "Check the MCP server with MCP Inspector".

**Tell Claude:**
- **The Inspector version** you used; Claude pins it in the instructions.
- **Whether sign-in worked.** Cognito may not publish `code_challenge_methods_supported`, which MCP clients on spec 2025-11-25 expect (Slice 0 heads-up). If Inspector refuses, send the error text. Claude would then serve the authorisation-server metadata from the app, which is a code change.
- **Whether the guided flow needs `/oauth/callback/debug`** added to the `mcp-inspector` client (Slice 0 nit G-5).

### 7. Browser sign-in on AWS
**What to do:** open the deployed app and sign in as a judge, then reload. Sign out, and sign in again. Wait more than an hour, or revoke a helper, then try a turn as that helper.

**Tell Claude:** anything that failed, plus three facts:
- **Did the redirect back to the app work?**
- **Do responses carry `Strict-Transport-Security`?** Check in DevTools → Network → the page → response headers. HSTS was deferred until this check.
- **After expiry or revocation, did the page say "You no longer have access…"** rather than "I lost the connection"?

These paths can't be tested locally (review items I9 and the Cognito error callback).

### 8. `make eval` results
**What to do:** `make run`, then `make eval`, with Bedrock credentials in your shell or `.env.eval`.

**Tell Claude:** the summary line, and the violations section of `evals/report.json`. Paste only that section, since the report holds model speech and no secrets, but check it anyway.

**What happens next:** zero tolerance applies (NFR-06). For each failure, Claude tightens the guard or the prompt, and adds the failing prompt to the unit tests.

### 9. Voice runs (`docs/voice-test-checklist.md`)
**What to do:** run AT-22, AT-13 (voice) and AT-23 with the screen hidden, and record them.

**Tell Claude:** any row that failed, plus:
- **the measured stop time;**
- **any read-back that seemed to end early.** "Yes" being accepted before HomeKeep finished speaking would point at the speech-end fallback, a verifier observation.

**What happens next:** Claude fixes the client and adds a stubbed E2E case for each failure.

### 10. Load run on AWS (optional)
**What to do:** if you want AT-29-style evidence from AWS, put three judge access tokens in a local file (never commit it). Then run `uv run python -m scripts.load --base-url <APP_URL> --token-file <file>`.

**Tell Claude:** the JSON output. Claude writes it up for the submission.

### 11. Clean-account run from the README (AT-32)
**What to do:** follow the README's "Deploy to AWS" and "Run it locally" sections exactly as written, ideally in a clean account or on a clean machine (HANDOFF §7).

**Tell Claude:** every step that was missing, wrong or unclear. Claude fixes the README and `docs/infra-contract.md`.

### 12. First CI run on GitHub
**What to do:** after your first push, check that the CI checks `lint`, `test`, `audit` and `gitleaks` pass on `main` (infra-contract §13).

**Tell Claude:** the name of any failing job and its log excerpt. Claude fixes it. CI has never run on GitHub's runners, only locally, so a first-run difference is possible.

## Content only you can provide (the submission)

### 13. Your words and evidence for Devpost
Claude can draft everything that comes from the repo. These need you:
- **`docs/submission/description.md`:** your personal line, the real challenges, and what you're proud of (the `TODO(Deb)` markers).
- **`docs/product-feedback.md`:** 64 `TODO(Deb)` slots. Some are about the AWS services you'll have used by then (ECS Express Mode, Cognito, Bedrock, DynamoDB) and some about onboarding.
- **`docs/friction-log.md`:** your AWS-side entries (provisioning, Express Mode, Cognito, Bedrock access). Claude can add the build-side ones from Slices 0–4, but only if you want them.
- **`docs/submission/built-with.md`:** trim to the tags Devpost offers.
- **The video:** record and upload it, using `docs/submission/video-script.md`.
- **The Devpost testing field:** real URLs and judge logins go only there, never in the repo.

**Your answer:**
- Should Claude **draft** the description, testing instructions and video-script sections from what's built, for you to edit?
- Should Claude **add build-side friction-log entries**? Candidates: FastAPI 0.143's lazy routers, Strands still using the deprecated MCP client, moto behaving differently from DynamoDB Local, and the Playwright and axe version clash.

## Your own work: where it is listed

This page is only what Claude needs from you. Your own tasks, which need nothing from Claude unless they go wrong, are in these documents:

| Document | What it covers |
| --- | --- |
| `docs/infra-contract.md` | Provisioning every AWS resource (§3–§12), the GitHub settings (§13), the outputs to record (§14), the AWS seed (§14.1), and the owner verification checklist (§15) |
| `docs/submission/checklist.md` | The submission end to end: key dates (**the credits request form closes 21 Oct, 12:00 PT**; the deadline is 23 Oct, 12:00 PDT), eligibility evidence, repository, MCP evidence, video and Devpost fields, friction log, and keeping it live until 20 Nov (budget, uptime check, teardown reminder) |
| `docs/voice-test-checklist.md` | The recorded voice runs (AT-22, AT-13 voice, AT-23) and stop timing |
| `docs/HANDOFF.md` §7 | What only you can verify: `make eval`, voice acceptance, the ECS Express Mode domain and networking cost, `/mcp` reachability, AT-32 |
| `README.md` | Deploy steps and the `hk-admin` operator commands, for running the demo |

Not in any document: commit and merge branch `post-slice-4-fixes`, then push to GitHub (you have not pushed any slice yet).

Whenever a step in those documents fails, or produces a result Claude asked for above, send it here.

## Done without you (branch `post-slice-4-fixes`, 17 Oct)

These needed no input and are fixed, with tests. They're on branch `post-slice-4-fixes` for you to commit and merge.

- **The Cognito web callback path:** the client now returns from sign-in to `${APP_BASE_URL}/auth/callback` and signs out to `${APP_BASE_URL}/`, exactly as infra-contract §5.3 registers them. The app serves the page at both paths.
- **Library log lines** (`httpx`, `httpcore`, `mcp`) are held at WARNING, so their request lines no longer reach CloudWatch.
- **Code nits:**
  - the opaque member-reference test now checks the format, per-household uniqueness, and that a raw subject is refused;
  - `speak()` no longer reports "completed" when nothing was spoken;
  - the sweep scopes its identity to the record's own partition and skips a record that disagrees (Slice 3 N5);
  - `CLOCK_OVERRIDE` refuses a bare epoch number.
- **Documentation:**
  - infra-contract §6.1's inference-profile ARN uses `${BEDROCK_REGION}`;
  - the testing instructions now have the voice and text journeys and the reset section;
  - the video script quotes the real template lines;
  - the description and built-with statuses match what's built;
  - S3 is no longer claimed (documents are deferred).

What still needs you is above: the Inspector version (item 6), and checking every step against the hosted demo (item 13).
