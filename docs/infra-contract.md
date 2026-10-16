# HomeKeep infrastructure contract (hackathon release H)

This is the checklist Deb provisions against, by console or CLI. There is no CDK or Terraform in H (decision P0-1, §16). Every resource, setting and environment variable the application expects is listed here. If the code needs something that is not on this page, the code is wrong or this page is out of date; fix one of them in the same change.

Sources: TDD §3.1, §5.2, §6, §9.1, §10.2, §10.4, §11; HANDOFF §2, §4, §5; `plans/slice-0.md`.

## 1 How to use this page

- Work top to bottom for each environment (`test` first, then `demo`).
- Values in `<ANGLE_BRACKETS>` or `${DOLLAR_BRACES}` are placeholders. Replace them only in the AWS console, in the ECS service's environment, in your password manager or in the Devpost form. **Never commit a real value to this repository** (it is public). That includes account IDs, user-pool IDs, client IDs, bucket names that embed an account ID, domains and passwords. gitleaks blocks the common shapes (`.gitleaks.toml`).
- Record each output in §14 as you go.
- Tick the owner checks in §15 during provisioning.

## 2 Naming and tags

| Item | Rule |
| --- | --- |
| Environment names | `test` (CI and QA; faults and clock override allowed) and `demo` (judges; no clock override) |
| Resource prefix | `homekeep-{env}`, for example `homekeep-demo` |
| Region | `us-east-1` for everything |
| Tags on every resource that supports them | `project=homekeep`, `env={env}`, `owner=<YOUR_HANDLE>` |

## 3 DynamoDB table

| Setting | Value |
| --- | --- |
| Table name | `homekeep-{env}`, passed to the app as `TABLE_NAME` |
| Partition key | `PK` (String) |
| Sort key | `SK` (String) |
| Global secondary index | Name `GSI1`; partition key `GSI1PK` (String); sort key `GSI1SK` (String); projection **ALL** |
| Time to live | Enabled on attribute `ttl` (epoch seconds) |
| Capacity mode | On-demand |
| Encryption at rest | Default (AWS owned key) |
| Streams | Off |

The table holds every item in TDD §6.1. One overloaded index serves both the staff queue and the reconciliation sweep (TDD §6.1, GSI1).

## 4 S3 bucket (documents)

| Setting | Value |
| --- | --- |
| Bucket name | `homekeep-{env}-docs-<RANDOM_SUFFIX>`, passed as `BUCKET_NAME`. Do not put the account ID in the name |
| Block Public Access | All four settings **on** |
| Object ownership | Bucket owner enforced (ACLs disabled) |
| Default encryption | SSE-S3 |
| Versioning | Off |
| Prefixes used by the app | `quarantine/` (uploads before validation) and `validated/` |

**Bucket policy (TLS only).** Replace `${BUCKET_NAME}`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ],
      "Condition": { "Bool": { "aws:SecureTransport": "false" } }
    }
  ]
}
```

**CORS.** Browsers upload by presigned POST from the app origin only. Replace `${APP_BASE_URL}` with the exact origin (scheme and host, no trailing slash). This is the CLI format for `aws s3api put-bucket-cors --cors-configuration file://cors.json`. In the console's CORS editor, paste only the array inside `CORSRules`.

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["${APP_BASE_URL}"],
      "AllowedMethods": ["POST"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
```

**Lifecycle.** CLI format, for `aws s3api put-bucket-lifecycle-configuration --lifecycle-configuration file://lifecycle.json`. In the console, create the same two rules in the Lifecycle rules form.

```json
{
  "Rules": [
    {
      "ID": "expire-quarantine",
      "Filter": { "Prefix": "quarantine/" },
      "Status": "Enabled",
      "Expiration": { "Days": 1 }
    },
    {
      "ID": "abort-incomplete-uploads",
      "Filter": { "Prefix": "" },
      "Status": "Enabled",
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 1 }
    }
  ]
}
```

## 5 Cognito

### 5.1 User pool

| Setting | Value |
| --- | --- |
| Name | `homekeep-{env}` |
| Self sign-up | **Off** (admin-created users only; `scripts/seed.py` creates them in a later slice) |
| Sign-in identifier | Username |
| Required attributes | None |
| MFA | Off (synthetic demo users) |
| Account recovery | None needed (seed resets judge passwords) |
| Prevent user-existence errors | On |
| Domain | Managed login with a Cognito prefix domain: `https://<DOMAIN_PREFIX>.auth.us-east-1.amazoncognito.com`. Passed as `COGNITO_DOMAIN` |

### 5.2 Resource server

| Setting | Value |
| --- | --- |
| Identifier | `homekeep` |
| Scopes | `api` (the elder, staff and admin REST API) and `mcp` (the MCP endpoint). Full scope names are `homekeep/api` and `homekeep/mcp` |

### 5.3 App clients

Both clients are **public**: no client secret.

| Setting | `web` | `mcp-inspector` |
| --- | --- | --- |
| Client secret | None | None |
| OAuth grant | Authorization code | Authorization code |
| PKCE | Always used by the client (S256) | Always used by the client (S256) |
| Scopes | `openid homekeep/api homekeep/mcp` | `homekeep/mcp` |
| Callback URLs | `${APP_BASE_URL}/auth/callback` | `http://localhost:6274/oauth/callback` |
| Sign-out URLs | `${APP_BASE_URL}/` | — |
| Identity provider | Cognito user pool | Cognito user pool |
| Auth flows | `ALLOW_USER_SRP_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH` | `ALLOW_USER_SRP_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH` |
| Token revocation | On | On |
| Access token lifetime | 60 minutes | 60 minutes |
| ID token lifetime | 60 minutes | 60 minutes |
| Refresh token lifetime | 1 day | 1 day |
| Env var for the client ID | `COGNITO_WEB_CLIENT_ID` | `COGNITO_MCP_CLIENT_ID` |

The callback and sign-out paths are fixed now so you can provision before Slice 4, and Slice 4 must use them (G-4). The `mcp-inspector` callback is MCP Inspector's default local callback; check it against the Inspector version you use (§15, G-5).

### 5.4 Groups

`coordinator`, `technician`, `catalog_reviewer`, `admin`. Household roles and grants are **not** groups; they live in DynamoDB (TDD §9.1).

### 5.5 What the server verifies on every access token

| Claim or check | Required value |
| --- | --- |
| Signature | Valid against `${COGNITO_ISSUER}/.well-known/jwks.json` |
| `iss` | `https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_USER_POOL_ID}` (the app derives this; it is not a separate variable) |
| `token_use` | `access` |
| `client_id` | `COGNITO_WEB_CLIENT_ID` or `COGNITO_MCP_CLIENT_ID` |
| `scope` | Contains `homekeep/mcp` for `/mcp`; contains `homekeep/api` for `/api/*` |
| `exp` | In the future |
| `cognito:groups` | Read for staff roles only; never for household scope |

Tenant scope comes only from the token subject → membership lookup in DynamoDB (CLAUDE.md invariant 1).

## 6 IAM

### 6.1 Task role `homekeep-{env}-task`

Trust policy principal: `ecs-tasks.amazonaws.com`. Replace every `${…}` placeholder. There are no wildcard resources. Items marked **P0-4** are additions to TDD §11.2, each with its reason in §16.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDbTableAndIndex",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:BatchWriteItem",
        "dynamodb:ConditionCheckItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${TABLE_NAME}",
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${TABLE_NAME}/index/GSI1"
      ]
    },
    {
      "Sid": "S3DocumentObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}/quarantine/*",
        "arn:aws:s3:::${BUCKET_NAME}/validated/*"
      ]
    },
    {
      "Sid": "S3ListDocumentPrefixesP04",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}",
      "Condition": {
        "StringLike": { "s3:prefix": ["quarantine/*", "validated/*"] }
      }
    },
    {
      "Sid": "BedrockHaikuInferenceProfile",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
      ]
    },
    {
      "Sid": "CognitoRevocationAndPurge",
      "Effect": "Allow",
      "Action": ["cognito-idp:AdminUserGlobalSignOut", "cognito-idp:AdminDisableUser"],
      "Resource": "arn:aws:cognito-idp:${AWS_REGION}:${ACCOUNT_ID}:userpool/${COGNITO_USER_POOL_ID}"
    }
  ]
}
```

Notes:

- **DynamoDB transactions.** IAM has no `dynamodb:TransactWriteItems` action. A transaction is authorised through the action of each item in it: `PutItem`, `UpdateItem` and `DeleteItem`, plus `ConditionCheckItem` for condition checks (DynamoDB developer guide, "Using IAM with DynamoDB transactions"). The policy therefore lists those instead.
- **Bedrock regions.** The three foundation-model ARNs are the US regions the `us.` profile is expected to route to. Check the profile's destination regions in the Bedrock console (Cross-region inference → the Haiku 4.5 US profile) and add or remove ARNs to match exactly (§15).
- Converse calls are authorised by `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`.

### 6.2 Task execution role `homekeep-{env}-exec`

Trust principal `ecs-tasks.amazonaws.com`, with the AWS managed policy `service-role/AmazonECSTaskExecutionRolePolicy` (ECR pull and CloudWatch Logs). No other permissions: the app reads no secrets.

### 6.3 Express Mode infrastructure role

Trust principal `ecs.amazonaws.com`, with the AWS managed policy `service-role/AmazonECSInfrastructureRoleforExpressGatewayServices`. ECS uses it only while it creates, updates or deletes the Express service.

## 7 ECR

| Setting | Value |
| --- | --- |
| Repository | `homekeep` (one repository; both environments) |
| Image tag | The git commit SHA (`git rev-parse --short=12 HEAD`). Never `latest` |
| Tag mutability | Immutable |
| Scan on push | On |
| Image platform | `linux/arm64` (`make build` produces it) |

## 8 Container and ECS Express Mode service

| Setting | Value |
| --- | --- |
| Service name | `homekeep-{env}` |
| Image | `<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/homekeep:<GIT_SHA>` |
| CPU architecture | ARM64 (Graviton) |
| Task size | 0.5 vCPU, 1 GB |
| Desired, minimum and maximum tasks | 1, 1, 1 (no autoscaling; TDD §11.3) |
| Container port | `8000` |
| Health check | `GET /healthz` → HTTP 200 with body `{"status":"ok"}`. It is a liveness check and makes no AWS calls |
| Uvicorn workers | Exactly 1 (set in the image; do not override the command) |
| Task role / execution role | §6.1 / §6.2 |
| Networking | Public subnets, no NAT gateway (S-1 check in §15) |
| Logs | CloudWatch Logs, group `/ecs/homekeep-{env}`, retention **30 days** |
| Forwarded headers | Uvicorn trusts `X-Forwarded-*` only from `127.0.0.1`, so behind the ALB the app sees its own URL as `http://…`. This is deliberate: the app builds every public URL (OAuth callbacks, Protected Resource Metadata, `WWW-Authenticate` `resource_metadata`) from `APP_BASE_URL`, never from the request. Do not set `FORWARDED_ALLOW_IPS` |
| Environment | §9 |

## 9 Environment variables

"Required in" lists the environments where the app refuses to start without the variable. A dash means it may be left unset there. `ENV=local` is the developer machine (`make run`), never AWS. Empty values count as unset.

| Variable | Required in | Example placeholder | Default | Purpose |
| --- | --- | --- | --- | --- |
| `ENV` | local, test, demo | `demo` | — | One of `local`, `test`, `demo`. Selects the rules below |
| `LOG_LEVEL` | — | `INFO` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `PORT` | — | `8000` | `8000` | Port Uvicorn listens on inside the container |
| `AWS_REGION` | — | `us-east-1` | `us-east-1` | Region for DynamoDB, S3 and Cognito. ECS on Fargate sets it automatically |
| `TABLE_NAME` | test, demo | `homekeep-demo` | `homekeep-local` when `ENV=local` | DynamoDB table (§3) |
| `BUCKET_NAME` | test, demo | `<BUCKET_NAME>` | — | S3 documents bucket (§4) |
| `DYNAMODB_ENDPOINT_URL` | local | `http://localhost:8001` | — | DynamoDB Local endpoint. **Allowed only when `ENV=local`**; the app refuses to start if it is set elsewhere |
| `COGNITO_USER_POOL_ID` | test, demo | `<COGNITO_USER_POOL_ID>` | — | User pool (§5.1). The issuer and JWKS URLs are derived from it and `AWS_REGION` |
| `COGNITO_DOMAIN` | test, demo | `https://<DOMAIN_PREFIX>.auth.us-east-1.amazoncognito.com` | — | Managed login base URL (§5.1). Public; served to the web client at `GET /config.json` from Slice 4 |
| `COGNITO_WEB_CLIENT_ID` | test, demo | `<COGNITO_WEB_CLIENT_ID>` | — | Public `web` client (§5.3). Public; served at `GET /config.json` from Slice 4 |
| `COGNITO_MCP_CLIENT_ID` | test, demo | `<COGNITO_MCP_CLIENT_ID>` | — | Public `mcp-inspector` client (§5.3); accepted as a token `client_id` on `/mcp` |
| `MODEL_ID` | — | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model or inference profile ID |
| `BEDROCK_REGION` | — | `us-east-1` | the value of `AWS_REGION` | Region of the Bedrock runtime endpoint |
| `MODEL_PROVIDER` | — | `bedrock` | `fake` when `ENV=local`, else `bedrock` | `bedrock` or `fake`. `fake` (the scripted test model, Slice 2) is **allowed only when `ENV` is `local` or `test`** |
| `APP_BASE_URL` | test, demo | `https://<APP_DOMAIN>` | `http://localhost:8000` when `ENV=local` | Public origin of the app: scheme and host (and port if not the default). A trailing slash or default port is removed; a path, query or credentials stop startup. Must be `https` in `demo`. Every public URL the app emits is built from it |
| `ALLOWED_ORIGINS` | test, demo | `https://<APP_DOMAIN>` | the value of `APP_BASE_URL` when `ENV=local` | Comma-separated origins accepted by the browser API and the `/mcp` Origin check. Each one is normalised like `APP_BASE_URL`; all must be `https` in `demo` |
| `MCP_LOOPBACK_URL` | — | `http://127.0.0.1:8000/mcp` | `http://127.0.0.1:${PORT}/mcp` | URL the orchestrator uses to call its own MCP server inside the task |
| `FAULTS_ENABLED` | — | `false` | `false` | Enables the admin-only provider fault injection (TDD §4.6) |
| `CLOCK_OVERRIDE` | — | `2026-10-20T18:29:00+00:00` | — | Fixed "now" as an ISO-8601 time with an offset. **Allowed only when `ENV=test`**; the app refuses to start if it is set elsewhere (G-3) |
| `DAILY_TURN_CAP` | — | `300` | `300` | Turns per household per day (NFR-12) |
| `MAX_TOOL_CYCLES` | — | `12` | `12` | Model/tool cycles per turn (NFR-12) |
| `TURN_BUDGET_SECONDS` | — | `20` | `20` | Wall-clock budget for one turn |
| `BEDROCK_PRICE_INPUT_PER_MTOK_USD` | — | `<PRICE_FROM_PRICING_PAGE>` | — | Optional. Input-token price for the Ops page cost estimate; the page shows "not configured" when unset |
| `BEDROCK_PRICE_OUTPUT_PER_MTOK_USD` | — | `<PRICE_FROM_PRICING_PAGE>` | — | Optional. Output-token price, as above |

`.env.example` lists exactly these variables, and `tests/unit/test_env_contract.py` fails if this table, `.env.example` and `app/config.py` drift apart.

## 10 Deliberately not configuration

| Item | Why |
| --- | --- |
| `SIMULATION_MODE` | A code constant, `"DEMO"`. There is no live provider adapter in H (CLAUDE.md invariant 3). The app refuses to start if a `SIMULATION_MODE` variable is set, so nobody can believe they switched it |
| Channel attestation key (`X-HK-Attest`) | Generated at process start, never leaves memory (TDD §5.3) |
| Household IDs | Come only from the token → membership lookup (invariant 1) |
| Any secret | None exist: public PKCE clients, task-role credentials, per-process attestation key. No Secrets Manager or SSM (TDD §3.3) |
| AWS access keys | Never set `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` on the service; the task role supplies credentials |

## 11 Bedrock model access

In `us-east-1`, open Bedrock → Model access and enable **Anthropic Claude Haiku 4.5**. Confirm the US inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0` is listed under Cross-region inference, and note its destination regions for §6.1.

## 12 Budgets

| Setting | Value |
| --- | --- |
| Budget | Monthly cost budget, USD 75, all services |
| Alerts | Actual cost at 50%, 80% and 100%, to `<OWNER_EMAIL>` |
| Also | A free external uptime check on `${APP_BASE_URL}/healthz` every 5 minutes until 20 November 2026 (TDD §10.4) |

## 13 GitHub repository settings

| Setting | Value |
| --- | --- |
| Visibility | Public |
| Licence | `LICENSE` (Apache-2.0) is detected and shown in the About panel |
| Branch protection on `main` | Require a pull request; require the CI checks `lint`, `test`, `audit` and `gitleaks` to pass |
| Actions | Enabled; default workflow permissions read-only |
| Secret scanning and push protection | On (free for public repos) |

## 14 Outputs to record

| Output | Where it goes |
| --- | --- |
| Account ID | Password manager only; substituted into the IAM JSON in the console |
| `TABLE_NAME`, `BUCKET_NAME` | ECS service environment |
| `COGNITO_USER_POOL_ID`, `COGNITO_DOMAIN`, `COGNITO_WEB_CLIENT_ID`, `COGNITO_MCP_CLIENT_ID` | ECS service environment; your local `.env.eval` for `make eval` (never `.env`, which `make run` loads; both are gitignored) |
| App URL (the Express Mode HTTPS domain) | `APP_BASE_URL` and `ALLOWED_ORIGINS` in the ECS environment; the Cognito `web` callback and sign-out URLs; the S3 CORS rule; Devpost "Testing instructions" (the field, not `docs/submission/testing-instructions.md`) |
| MCP URL (`${APP_BASE_URL}/mcp`) | Devpost testing instructions field; MCP Inspector |
| ECR repository URI | Your shell when tagging and pushing an image |
| Judge usernames and passwords (Slice 4 seed) | Password manager and the Devpost field only |

## 15 Owner verification checklist

- [ ] **S-1:** ECS Express Mode is the resource type used for the service, and the console or CLI shows its name.
- [ ] **S-1:** the service gets an AWS-provided HTTPS domain, and `curl -fsS https://<APP_DOMAIN>/healthz` returns `{"status":"ok"}`.
- [ ] **S-1:** the service runs in public subnets with no NAT gateway created (check VPC → NAT gateways).
- [ ] **S-1:** ARM64 at 0.5 vCPU / 1 GB is accepted, and the running task shows `ARM64`.
- [ ] **Bedrock:** the US Haiku 4.5 profile's destination regions match the foundation-model ARNs in §6.1.
- [ ] **G-5:** the `mcp-inspector` callback URL matches the Inspector version you run (its OAuth settings panel shows the redirect URL).
- [ ] The IAM task-role policy passes the IAM policy editor's validation with no errors.
- [ ] S3: an `http://` request to the bucket is denied; Block Public Access shows all four settings on.
- [ ] Cognito: self sign-up is off; token lifetimes read 60 min / 60 min / 1 day on both clients.
- [ ] The log group retention reads 30 days.
- [ ] The budget and its three alerts exist.
- [ ] No real value from this checklist was pasted into the repository.

## 16 Deviations from the TDD

The TDD stays read-only; these are recorded here and in HANDOFF §1.

| ID | Deviation | TDD reference | Reason |
| --- | --- | --- | --- |
| P0-1 | No CDK and no `infra/`. This page is the provisioning checklist; there are no `make bootstrap`, `deploy` or `destroy` targets. For AT-32 the README points here | §4.1, §11.1, §11.5 steps 2 and 7 | Schedule: provisioning by hand against an exact checklist is faster for one owner than writing and debugging a stack |
| P0-3 | Node 24 LTS in the image, `.nvmrc` and README | §11.5 step 1 (Node 20) | Node 20 has been end of life since 30 April 2026 |
| P0-4 | Task role adds `dynamodb:ConditionCheckItem`, `s3:ListBucket` (prefix-conditioned) and `cognito-idp:AdminDisableUser`, and lists no `dynamodb:TransactWriteItems` | §11.2 | `ConditionCheckItem`: the condition checks inside booking transactions (TDD §6.2) need it, and IAM authorises transactions per item action. `ListBucket`: purge must find a household's objects under both prefixes (FR-24). `AdminDisableUser`: purge disables the household's Cognito users (TDD §6.2) |
| P0-5 | The web client gets its public Cognito config (domain, client ID, scopes) at runtime from `GET /config.json`, built from the env vars in §9. The route lands in Slice 4 | Not covered by the TDD | One image serves both environments; nothing environment-specific is baked into the web bundle |
| G-3 | `CLOCK_OVERRIDE` set outside `ENV=test` stops the app at startup instead of being ignored | §4.5 ("honoured only when `ENV=test`") | Silently ignoring it would hide a misconfiguration |
