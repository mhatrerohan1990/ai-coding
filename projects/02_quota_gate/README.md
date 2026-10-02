# Quota Gate (take-home)

**Role:** Senior Software Engineer
**Time box:** 3 hours of work. You may use AI; record how in `NOTES.md`.
**Follow-up:** a 30–40 min walkthrough. **We will change a requirement live.**

## Context

You are building **Quota Gate**, an internal HTTP service that other Okta-like APIs call
*before* they do expensive work ("may user_9 in org_1 run `users.export` right now?").

A request is identified by:

- `tenant_id`: the org, e.g. `org_1`
- `subject`: a user id, client id, or `anonymous`
- `action`: e.g. `auth.login`, `users.export`, `api.read`

Each tenant has policies. A request is allowed only if every policy that applies to it still has quota.

This folder contains a skeleton (`run.py`, `quota_gate/app.py` with `/healthz`) so you don't spend
time on boilerplate. You can replace any of it, including the framework, as long as you keep the
**run contract** below.

---

## 1. Policies (admin API)

```
PUT    /v1/tenants/{tenant_id}/policies/{policy_id}
GET    /v1/tenants/{tenant_id}/policies/{policy_id}
DELETE /v1/tenants/{tenant_id}/policies/{policy_id}
Authorization: Bearer <token with scope quota.admin>
```

```json
{
  "match":  { "subject": "*" | "<id>", "action": "*" | "<action>" },
  "limit": 100,
  "window_seconds": 60,
  "burst": 20
}
```

- **Token bucket.** `burst` is the bucket capacity (the most tokens that can sit unused). The bucket
  refills continuously at `limit / window_seconds` tokens per second. A new bucket starts **full**.
- `policy_id` matches `^[a-z0-9][a-z0-9_-]{0,63}$`.
- `limit`, `window_seconds` and `burst` are integers ≥ 1. `window_seconds` ≤ 86400.
- PUT is an upsert: `201` when created, `200` when replaced. The response body is the stored policy
  (including `policy_id` and `tenant_id`). GET returns the same shape. DELETE returns `204`.
- Invalid bodies get `400` with a clear error (see *Error shape*).

**Which policies apply to a check.** A policy *matches* when each of its `match` fields is `*` or equal
to the request's value. Specificity of a match:

| match.subject | match.action | specificity |
|---|---|---|
| exact | exact | 3 |
| exact | `*` | 2 |
| `*` | exact | 1 |
| `*` | `*` | 0 |

Only the matching policies with the **highest** specificity apply. If several tie, **all** of them apply
(AND): the request is allowed only if every one has enough tokens.

## 2. Check (hot path)

```
POST /v1/check
Authorization: Bearer <token with scope quota.check>
```

```json
{ "tenant_id": "org_1", "subject": "user_9", "action": "users.export", "cost": 1 }
```

`cost` is optional (default 1); when present it must be an integer ≥ 1.

**200** when allowed, **429** when denied, with the same body (`allow: false` on 429):

```json
{
  "allow": true,
  "remaining": 17,
  "reset_at": 1727740800,
  "matched_policies": ["export-cap"]
}
```

- `remaining`: whole tokens left in the most constrained applied policy, after this request.
- `reset_at`: unix seconds when that policy's bucket will be full again.
- `matched_policies`: ids of the applied policies.

Headers on both 200 and 429: `X-RateLimit-Limit` (the `limit` of the most constrained applied policy)
and `X-RateLimit-Remaining`. On 429, also `Retry-After`: whole seconds (≥ 1) until the request could
succeed.

**Concurrency:** checks must be safe under concurrent requests. Two simultaneous checks must never both
see `remaining=1` and both be allowed.

## 3. AuthN / AuthZ (the Okta part)

Every `/v1` endpoint requires `Authorization: Bearer <JWT>`.

- **HS256** with a shared secret is fine for this exercise. Explain in your notes why you wouldn't ship it.
- Validate the signature and these claims:

  | claim | rule |
  |---|---|
  | `iss` | equals the configured issuer (`QUOTA_GATE_ISSUER`) |
  | `aud` | `api://quota-gate` (a string, or a list containing it) |
  | `exp` | in the future |
  | `sub` | a non-empty string |
  | `tid` | a non-empty string: the tenant the token belongs to |
  | `scp` | a list of scopes (Okta access-token style), e.g. `["quota.admin"]` |

- The admin principal is `(iss, tid, sub)`. Admin endpoints need scope `quota.admin`; check needs `quota.check`.
- **Tenant binding:** a token with `tid=org_1` must not read or write `org_2` policies, or consume
  `org_2` quota.
- Incoming `X-Tenant-Id` / `X-User` headers are **untrusted**. Identity comes from the JWT only.
- `check` is usually called with a *service* token (client credentials: `sub` is a client id) that has
  `quota.check` and a `tid`. It may only check that tenant.
- **Missing or invalid JWT → 401, never 500.** Valid token but not allowed → 403.

Include a small helper script (or README curl examples) that mints tokens for `org_1` and `org_2`.

## 4. Persistence

- **Policies must survive a restart.** Use SQLite (or a file).
- Counters (buckets) may live in memory and reset on restart. Document that.

## Non-functional

- `check` must stay cheap: no full table scan per request.
- Abandoned or unused buckets must not grow memory forever (TTL or an equivalent).
- Errors have one JSON shape everywhere:

  ```json
  { "error": { "code": "invalid_request", "message": "limit must be an integer >= 1" } }
  ```

  Codes: `invalid_request` (400), `invalid_token` (401), `forbidden` (403), `not_found` (404).
  The 429 from `check` uses the check body, not this shape.

## Open questions: you decide, and write the decision down

The spec deliberately leaves these open. Pick an answer for each, implement it, and be ready to defend it.

1. A check where **no policy matches**: allow or deny?
2. Is a `subject: "*"` policy **one shared bucket** for the whole tenant, or **one bucket per subject**?
3. When a policy is **replaced** (PUT on an existing id), what happens to its current bucket?
4. A check whose `cost` is larger than a policy's `burst` can never succeed. What do you return?
5. Specificity 2 vs 1: is that ordering right for a rate limiter? Would you change it?

## Out of scope (do not build)

Multi-region replication, UI, real KMS / JWKS rotation, a distributed Redis cluster.
A short note on how you'd add them is welcome.

---

## Run contract (the grader depends on this)

From this folder:

```bash
QUOTA_GATE_PORT=8080 \
QUOTA_GATE_DB=./quota_gate.db \
QUOTA_GATE_JWT_SECRET=dev-secret-change-me \
QUOTA_GATE_ISSUER=https://idp.example.test \
python run.py
```

- All four env vars have the defaults shown above.
- `GET /healthz` returns 200 without auth once the server is ready.
- The server must handle concurrent requests (the skeleton's threaded Flask server does).

## Tests we will run (a subset)

- Two concurrent checks against `limit=1` → exactly one allowed.
- A token for org_1 cannot PUT a policy on org_2.
- An ID-token-shaped JWT with `aud=spa` is rejected.
- After the window refills, checks succeed again.
- Missing or invalid JWT → 401, never 500.

## What we grade

1. Correctness under concurrency
2. Tenant binding / confused-deputy resistance
3. API clarity and error shape
4. Judgment: what you scoped out and why
5. Whether you can explain your code, and change it live

## Deliverables (in `NOTES.md`)

How to run and test, decisions for the open questions, known gaps, and an **AI log** (tools used, what
you kept, what you threw away and why).
