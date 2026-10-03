# Quota Gate notes

Start time: 1 AM
End time: 2:27 AM

## 1. Plan



Built test-first, one thin slice at a time, each slice red -> green before the next:

1. Policies CRUD happy path (in-memory, no auth).
2. Shared error classes + one JSON error shape.
3. JWT verification + tenant binding on the policy routes.
4. `/v1/check` happy path (stateless), then moved into a service layer.
5. SQLite persistence behind a repository interface; indexed match lookup.
6. Stateful token buckets: decrement, 429 + `Retry-After`, refill, concurrency safety.
7. Input validation, strict-match decision, catch-all JSON errors.
8. Open questions 3, 4, 5 (bucket reset on replace, cost > burst, specificity + AND ties).
9. Idle-bucket eviction (TTL + hard cap).

Would have cut if short on time: eviction (slice 9), then the migration of old SQLite files.

Layout:

```
quota_gate/app.py         HTTP only: routes, auth decorators, response shaping
quota_gate/auth.py        JWT verification, Principal, requires_scope guard
quota_gate/validation.py  request parsing / validation
quota_gate/services.py    PolicyService, CheckService (specificity, AND, retry math)
quota_gate/repository.py  PolicyRepository protocol + SQLite implementation
quota_gate/buckets.py     in-memory token buckets (atomic multi-bucket take, eviction)
quota_gate/errors.py      ApiError classes + JSON error handlers
scripts/mint_token.py     mint dev JWTs
```

## 2. Open questions: decisions

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | No policy matches | **Deny.** `429`, `allow: false`, `matched_policies: []`, `remaining: 0`, `Retry-After: 1`, no `X-RateLimit-*` headers. | Matching is strict: no policy means the caller was never granted the action. A wildcard policy (`*`/`*`) is how a tenant opts into "everything". Cost: a new tenant must create a policy before anything works. `Retry-After: 1` is a bit of a lie (waiting won't help) but the spec requires it on every 429. |
| 2 | `subject: "*"`: shared or per-subject bucket | **Per subject.** Bucket key is `(tenant, policy_id, subject)`. | One shared bucket lets a single noisy or compromised user exhaust the tenant's whole quota. Cost: bucket count grows with distinct subjects, handled by eviction (section 5). |
| 3 | Policy replaced: bucket | **Reset** every subject's bucket for that policy (also on DELETE). The next check starts from a full bucket at the new `burst`. | Counters accumulated under the old limits are meaningless under new ones. Reset on DELETE too, otherwise delete + re-create would resurrect old counters. Other policies and other tenants' same-id policies are untouched. Trade-off: re-PUTting (even an identical body) restores quota. |
| 4 | cost > burst | **400 `invalid_request`** naming the policy and both numbers, checked before any bucket is touched. | It can never succeed, so waiting is pointless; 429 + `Retry-After` would send clients into an endless retry loop. Applies if the cost exceeds the burst of *any applied* policy (outranked policies do not count). `cost == burst` on a full bucket is allowed. |
| 5 | Specificity order | **Keep the spec's order**: exact subject (2) beats exact action (1). Highest specificity wins; ties all apply (AND). | Predictable "the user-specific rule wins" and the common case is per-user overrides. Known weakness: a generous per-user policy (2) bypasses a safety cap on an expensive action (1). Guardrails should then be written as exact/exact policies, or I would switch to "apply every matching policy, most restrictive wins". |

Other decisions made along the way:

- **PUT is strict**: unknown fields are rejected, including `tenant_id` / `policy_id` in the body.
  (Before validation existed, a body could overwrite the stored `tenant_id`.) **Check is lenient**:
  unknown fields are ignored because callers on the hot path may add their own.
- **Order of failure**: 401 (token) -> 403 (scope, then tenant) -> 400 (body). An invalid check
  consumes no quota.
- **Several applied policies (ties)**: all-or-nothing. A request is charged to every applied bucket
  only if every one can afford it. `remaining`, `X-RateLimit-Limit` and `reset_at` come from the
  most constrained policy (fewest tokens left; ties broken by lowest `policy_id`). `Retry-After`
  is the longest wait among the policies that said no, minimum 1.
- **Extra error code**: `405` uses `method_not_allowed`, which is not one of the four in the spec.
- **Unexpected exceptions** return a JSON 500 `internal_error` with a generic message; details go to the log only.

## 3. How to run and test

```bash
# from projects/02_quota_gate, using the shared venv (flask, pyjwt, pytest)
QUOTA_GATE_PORT=8080 \
QUOTA_GATE_DB=./quota_gate.db \
QUOTA_GATE_JWT_SECRET=dev-secret-change-me \
QUOTA_GATE_ISSUER=https://idp.example.test \
../../.venv/bin/python run.py          # these four are the defaults

../../.venv/bin/python -m pytest       # 310 tests, ~1s
```

Mint tokens and try it:

```bash
PY=../../.venv/bin/python
ADMIN=$($PY scripts/mint_token.py org_1 quota.admin 2>/dev/null)
CHECK=$($PY scripts/mint_token.py org_1 quota.check 2>/dev/null)
H=http://127.0.0.1:8080; J='Content-Type: application/json'

curl -i -X PUT $H/v1/tenants/org_1/policies/export-cap -H "Authorization: Bearer $ADMIN" -H "$J" \
  -d '{"match":{"subject":"*","action":"users.export"},"limit":100,"window_seconds":60,"burst":20}'
curl -i $H/v1/tenants/org_1/policies/export-cap -H "Authorization: Bearer $ADMIN"
curl -i -X POST $H/v1/check -H "Authorization: Bearer $CHECK" -H "$J" \
  -d '{"tenant_id":"org_1","subject":"user_9","action":"users.export","cost":1}'
curl -i -X DELETE $H/v1/tenants/org_1/policies/export-cap -H "Authorization: Bearer $ADMIN"
```

`scripts/mint_token.py [--partner] [tenant] [scope ...]` (default `org_1 quota.admin`, 1 hour expiry).
It uses the same env vars as the server. `--partner` mints a token from the partner IdP (default
tenant `org_3`) and needs `QUOTA_GATE_PARTNER_SECRET`.

Partner IdP (follow-up requirement, section 4b): set `QUOTA_GATE_PARTNER_SECRET` to enable it
(optionally `QUOTA_GATE_PARTNER_ISSUER`, default `https://partner.example`). It has **no default**:
when unset, the partner issuer is simply not trusted.

Test layout (`tests/`): auth, policies, validation, errors, check, specificity, cost-vs-burst,
buckets (incl. concurrency), bucket eviction, repository, persistence (restart), services.
Time is injected (`create_app(..., clock=)`), so refill/expiry tests never sleep.

**Persistence**: policies live in SQLite and survive restarts. **Counters (buckets) are in memory
and reset on restart.** That is allowed by the spec; effect: after a restart every subject briefly
gets a full burst again.

## 4. Security notes

**Why not HS256 in production.** HS256 is a shared secret: every service that can *verify* a token
can also *mint* one, so compromise of any verifier (or a leaked env var) lets an attacker forge an
admin token for any tenant. There is no `kid` / rotation story either. In production the IdP
would sign with an asymmetric key (RS256 / ES256) and Quota Gate would only hold the public key,
fetched from the IdP's JWKS endpoint and cached, so keys can rotate without redeploying.
The dev secret (`dev-secret-change-me`, 20 bytes) is also below the 32 bytes RFC 7518 recommends
for HS256, hence the PyJWT `InsecureKeyLengthWarning` when minting.

**What is verified.** Signature with the algorithm pinned to HS256 (so `alg: none` and algorithm
confusion are rejected); `exp`, `iss`, `aud`, `sub` required; `iss` is one of the trusted issuers and the signature is
checked with *that issuer's own* secret (see 4b);
`aud` is `api://quota-gate` (string or list), so an ID-token-shaped JWT with `aud=spa` is rejected;
`sub` and `tid` non-empty strings; `scp` a list of strings. Any failure is a 401 `invalid_token`,
never a 500.

**Tenant binding / confused deputy.** The tenant is taken from the signed `tid` claim only. The
tenant named in the URL (admin API) or in the body (`/v1/check`) is compared with it and a
mismatch is a 403. `X-Tenant-Id` / `X-User` headers are never read. A token for `org_1` therefore
cannot read, write or delete `org_2` policies, or consume `org_2` quota. The same 403 is returned
whether or not the other tenant or policy exists, so it does not reveal what exists. Scopes are
separate: `quota.admin` cannot call check and `quota.check` cannot call the admin API.

**Trust boundary I accepted.** `/v1/check` trusts a `quota.check` service token about *which end
user* (`subject`) it is checking. A compromised `org_1` service token can burn any `org_1` user's
quota (denial of service within its own tenant) but cannot touch another tenant. Binding `subject`
to the token would need a different token model (per-user tokens), which defeats the use case.

Other: no token revocation (tokens are valid until `exp`); no clock-skew leeway; the Werkzeug dev
server is not a production server (use gunicorn/uvicorn behind TLS); the admin principal is
`(iss, tid, sub)` but it is not yet written to an audit log.

### 4b. Follow-up requirement: partner IdP for org_3

> Partner org_3 uses its own identity provider, `https://partner.example`, which signs with a
> different secret (`QUOTA_GATE_PARTNER_SECRET`). Tokens from that issuer may act only on org_3.
> Tokens from our issuer may act on any tenant except org_3. Everything else stays the same.

**What changed** (`auth.py`, `app.py`, `run.py`; the services, buckets and repository were untouched):

- `TokenVerifier` now takes a list of `TrustedIssuer(issuer, secret, only_tenants / except_tenants)`.
  Ours: `except_tenants={org_3}`. The partner's: `only_tenants={org_3}`.
- Verification picks the key from the token's `iss`, but the unverified `iss` is used **only as a
  lookup key into our own configured issuers**. Unknown / non-string / differently-cased issuers are
  a 401. The signature is then verified with that issuer's secret *and* `iss` must equal that
  issuer, so a token can never be checked against another issuer's secret (no cross-signing).
- `Principal.require_tenant` now enforces two things: tenant binding (token `tid` == tenant acted on,
  unchanged) **and** the issuer's tenant rule. Either failure is a 403 (valid token, not allowed).
  Order stays 401 -> 403 -> 400.
- Partner tokens get exactly the same claim validation, scopes (`quota.admin` / `quota.check`) and
  error shapes as ours; the partner's quota is independent of every other tenant's.

**Interpretation I chose:** "any tenant except org_3" does *not* relax tenant binding. An `org_1`
token still cannot touch `org_2`; the issuer rule is an extra restriction on top ("everything else
stays the same"). Consequently our issuer can never act on org_3 even when `tid=org_3`, and a
partner-signed token claiming `tid=org_1` is refused even though its `tid` matches the path.

**Decisions / threat model**

- **No default partner secret.** A guessable default would let anyone forge an org_3 admin token.
  Unset or empty means the partner issuer is not trusted at all. Our issuer stays barred from
  org_3 either way (fail closed). A test tries the obvious guesses against an unconfigured partner.
- **Startup guard:** the partner issuer must differ from ours (`ValueError`), otherwise one issuer
  entry would silently shadow the other.
- **Blast radius of a leaked secret shrinks:** a leaked partner secret can only ever yield org_3
  access; a leaked secret of ours can never yield org_3 access. Under the old single-issuer model
  either would have meant everything.
- Tenant ids are compared exactly, so `ORG_3` is just another tenant (and our issuer may use it).
  If tenant ids should be case-insensitive that is a decision to make upstream, not here.
- Verified by mutation: removing either tenant rule, never enforcing the rule, checking every token
  with one secret, or trusting the partner with a default secret each fails tests.

## 5. Known gaps / what I scoped out

- **Float token arithmetic.** Buckets use floats and report `floor(tokens)`. A rate like 100/60
  could in theory leave a token count a hair under a whole number. Not seen in practice; the fix is
  integer micro-tokens.
- **One global lock** in `BucketStore`. Correct and simple, but all checks serialise, and a sweep
  (every 60 s) scans every bucket under the lock, so the pause grows with bucket count. Fix: shard
  the lock by key, or keep a time-ordered heap of `full_at` instead of scanning.
- **Eviction is lossless, the hard cap is not.** An idle bucket is dropped only when it is full
  again, which changes no decision. Over `max_buckets` (500k) the buckets closest to full go
  first; an evicted but not-yet-full subject gets a free refill (fails open for that subject only).
- **A new SQLite connection per call** (`BEGIN IMMEDIATE` for writes). Fine at this scale; next
  step is a per-tenant in-memory policy cache invalidated on PUT/DELETE, or a connection pool + WAL.
- **Retried identical PUT resets the bucket** (see decision 3). Resetting only when the body changed is a one-line change.
- **Small race**: a check that read the old policy a moment before a PUT can create one bucket with
  the old `burst`; it self-corrects on the next check because refill clamps to the new capacity.
- **Not persisted: counters.** Lost on restart (allowed).
- **No pagination / list endpoint**, no metrics, no audit log, no rate limiting of the admin API itself.
- **Body must be `application/json`**; a missing or wrong content type is a 400, not a 415.

Out of scope per the README, and how I would add them:

- **Multi-region / multiple instances**: counters must be shared. Redis with one atomic Lua script
  per check (refill, check-all, deduct-all) and `EXPIRE` set to the time-until-full, which is the
  same rule as the in-memory eviction. Policies in DynamoDB or SQL with a short-TTL cache per node.
- **DynamoDB for policies**: `PolicyRepository` is already shaped for it. Partition key `tenant_id`,
  sort key `policy_id`, plus a secondary index on `(tenant_id, match_subject, match_action)`.
  `find_matching` becomes at most four exact-key lookups.
- **KMS / JWKS rotation**: verify RS256/ES256 against cached JWKS keyed by `kid`, refresh on unknown `kid`.
- **UI**: none needed; the admin API is the contract.

## 6. AI log

Tool: Claude Code (Sonnet 5.5), one long session, test-driven: I asked for one slice at a time and
the assistant wrote the failing tests first, then the code, then ran the suite.

What the human decided (the assistant proposed, the human chose):

- Build incrementally, TDD, happy path first with no algorithm.
- Service layer separate from the app layer; shared error/response helpers.
- A tenant-extraction helper so a token can only act on its own tenant (became `auth.py`).
- SQLite for this exercise behind an interface, DynamoDB as the "ideal" (became `PolicyRepository`).
- Q2 per subject; Q3 reset the bucket on replace; Q5 keep the spec's order.
- **Q1: the assistant's first version allowed a check with no matching policy. The human reversed
  it to deny ("we explicitly and strictly match on policy").** Code and tests were changed.
- **Q4: the assistant recommended 400 over a 429 with a misleading `Retry-After`; the human agreed.**

What I should be able to defend (the assistant's work, reviewed with the human):

- Test-first slices, and mutation checks on the risky parts: I broke the lock, the all-or-nothing
  charge, the specificity weights, `Retry-After` max/min, the most-constrained choice and the
  eviction rules, and confirmed the tests fail each time. Concurrency tests (48 parallel checks on
  `burst=1` -> exactly one 200) were verified to fail without the lock.
- Caught while building: PUT bodies could overwrite `tenant_id` (fixed by strict validation); a
  malformed `match` returned a 500 from a DB `IntegrityError`; an empty injected `BucketStore`
  was falsy once it had `__len__`, so `store or BucketStore()` silently dropped it (now `is None`).
- Mistakes by the assistant that got fixed: a first 4xx test helper that left a junk line in a test;
  a test that re-checked a bucket at the wrong refill rate (the test, not the store, was wrong);
  a malformed mutation that silently did not run until re-done; an early claim that `quota_gate.db`
  needed gitignoring (it was already covered by `*.db`).
- An indentation error appeared in `quota_gate/app.py` after the assistant's last green run
  (probably an editor change); the human hit it on `run.py`, the assistant fixed that one line.

Follow-up (live requirement change, partner IdP for org_3): done test-first in the same session;
the design is in section 4b. The assistant's first test run caught two bugs in its own tests
(PyJWT refuses to *encode* a non-string `iss`, so those tokens are hand-signed at the JWS level; a
duplicated keyword argument), and mutation testing exposed a missing test for the "unconfigured
partner with a guessable secret" case, which was then added.

What was thrown away / not built, and why: a per-tenant policy cache (the indexed SQLite lookup
was enough for now), a heap-based eviction (a periodic sweep is simpler), and a tenant-wide shared
bucket option (listed as a possible live requirement change, not needed).

