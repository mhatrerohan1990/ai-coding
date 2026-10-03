# Tenant invites (gudgeon)

Tenant invite service (FastAPI + SQLAlchemy + SQLite).

An admin creates a single-use invite for an email address in their tenant. The admin sends
the link themselves (this service doesn't send email). When the invitee redeems the token,
a user record is created (or reused) and they become a member of the tenant. The token is
then dead.

## Endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /tenants/{tenant_id}/invites` | JWT, `role=admin`, `tid == tenant_id` | Create (or re-issue) an invite. Does **not** create a member. |
| `POST /invites/accept` | none; the token in the body is the credential | Redeem a token: find-or-create user, add as member, burn the token. |
| `GET /tenants/{tenant_id}/members` | JWT, `role` in `admin`/`member`, `tid == tenant_id` | List the tenant's members. |
| `GET /health` | none | Liveness. |

## Authentication and authorization

`Authorization: Bearer <JWT>`, HS256 (algorithm pinned, so `alg: none` and other algorithms
are rejected), signed with `JWT_SECRET`.

Required claims: `exp`, `aud`, `sub`, `tid` (tenant id), `role` (`admin` or `member`).
`aud` must be `api://invites` (a list is accepted if it contains it). Anything else, such as
`aud=spa`, is a 401.

- **401**: missing header, non-Bearer scheme, bad signature, expired, wrong/missing `aud`,
  missing claim.
- **403**: the token's `tid` does not equal the `{tenant_id}` in the path (exact match), or
  the role is not allowed for the endpoint.
- Authn runs before authz, and both run before body validation.

**Decision: listing members is open to both `member` and `admin`** (of the token's own
tenant). Creating invites is admin-only. This is covered by tests in `tests/test_auth.py`.

`/invites/accept` is intentionally unauthenticated. The invitee isn't logged in yet, and
any `Authorization` header sent to it is ignored.

## Invite tokens

- Format `<invite_id>.<secret>`. `secret` is 256 bits from `secrets.token_urlsafe(32)`.
  `invite_id` is a random indexed lookup key.
- Only the SHA-256 hash of the secret is stored, never the token. The token is returned once,
  in the create response.
- Accept looks the invite up by `invite_id`, then compares hashes with `hmac.compare_digest`.
- Default expiry is 7 days (`INVITE_TTL` in `app/config.py`).
- **One pending invite per `(tenant_id, email)`**, enforced by a partial unique index.
  Creating again returns the *same* `invite_id` with a *new* token (the old token stops
  working) and resets the expiry. Emails are normalized to lowercase.
- Used invites are kept (with `used_at`) as an audit trail. Cleanup of old rows is not
  implemented.

## Accept semantics

Single-use is enforced by one atomic statement,
`UPDATE invites SET used_at = now WHERE id = ? AND used_at IS NULL AND expires_at > now`,
inside the same transaction that creates the user and member. Two concurrent accepts of one
token yield exactly one member.

| Case | Response |
|---|---|
| Success | `201` with the member |
| Malformed, unknown, wrong secret, expired, or re-issued (replaced) token | `400 Invalid or expired invite.` (deliberately one message) |
| Valid token already used (sequential or concurrent loser) | `409 This invite has already been used.` |
| Email is already a member of this tenant | `409 You are already a member of this tenant.`, nothing stored, invite stays unused |

A user can belong to many tenants (one membership per `(tenant, user)`).

## Setup and run

Either use the repo's shared venv (see the root README) or this project's own `pyproject.toml`
with [uv](https://docs.astral.sh/uv/). Run everything from `projects/03_tenant_invites/`.

```bash
export JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
python run.py                                  # shared venv
# or: uv sync && uv run uvicorn app.main:app --port 8000
```

API docs at http://127.0.0.1:8000/docs. The server refuses to start without `JWT_SECRET`.
The SQLite DB (`gudgeon.db`) and its tables are created on startup. There are no
migrations; delete the file to reset.

## Tests

```bash
python -m pytest        # shared venv
# or: uv run pytest
```

No environment setup needed; the tests set their own secret and use in-memory or temp-file
SQLite. Includes concurrency tests (10 threads racing one token, over HTTP and at the service
level).

## Try it by hand

Nothing in this app issues JWTs, so mint one with the helper (same `JWT_SECRET` as the server):

```bash
B=http://127.0.0.1:8000; H='Content-Type: application/json'
tok() { python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])'; }
ADMIN=$(python scripts/mint_token.py --tid t1 --role admin)

# create an invite (admin of t1)
T=$(curl -s -X POST $B/tenants/t1/invites -H "$H" -H "Authorization: Bearer $ADMIN" \
  -d '{"email":"ann@x.com"}' | tok)

# accept it: no JWT (201, then 409 on replay)
curl -s -w ' [%{http_code}]\n' -X POST $B/invites/accept -H "$H" -d "{\"token\":\"$T\"}"
curl -s -w ' [%{http_code}]\n' -X POST $B/invites/accept -H "$H" -d "{\"token\":\"$T\"}"

# list members
curl -s $B/tenants/t1/members -H "Authorization: Bearer $ADMIN"

# wrong tenant -> 403
curl -s -w ' [%{http_code}]\n' -X POST $B/tenants/t2/invites -H "$H" \
  -H "Authorization: Bearer $ADMIN" -d '{"email":"x@x.com"}'
```

(In zsh, don't paste trailing `# comments` onto a command line; curl treats them as URLs.)

Inspect the DB:

```bash
sqlite3 gudgeon.db 'select id, tenant_id, email, used_at from invites'
sqlite3 gudgeon.db 'select tenant_id, user_id, role from members'
```

## Layout

```
app/
  main.py          # app, startup checks, error -> HTTP mapping
  auth.py          # JWT authn + tenant/role authz dependencies
  tokens.py        # token generation, hashing, parsing, constant-time verify
  errors.py        # domain errors
  models.py        # User, Member, Invite tables
  schemas.py       # request/response models
  routers/         # HTTP layer
  services/        # business logic (invites, members)
scripts/mint_token.py   # mint a test JWT
tests/
```

## Not implemented / notes

- No token issuance, email sending, invite revocation or listing, or rate limiting.
- Tenants are not a table; `tenant_id` is a string taken from the JWT and path.
- Expired and used invites are never purged.
- No migrations (`create_all` at startup). SQLite is for the exercise; the partial unique
  index and atomic update also work on Postgres.
