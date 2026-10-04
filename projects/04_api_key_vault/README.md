# API key vault

Multi-tenant API key vault (FastAPI + SQLite). An admin creates API keys for machine
clients and gets the raw key back once; later introspect calls say whether a key is active.

## Endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /tenants/{tenant_id}/keys` `{name}` (1-50 chars after trimming; else 422) | JWT `role=admin`, scope `create` | Create a key. Returns `{key_id, secret, prefix}`; the raw key is shown once. |
| `POST /tenants/{tenant_id}/keys/{key_id}/revoke` | JWT `role=admin`, scope `revoke` | Revoke. 204, also when already `REVOKED` or while `ROTATING`; the next introspect is inactive. |
| `POST /tenants/{tenant_id}/keys/{key_id}/rotate` | JWT `role=admin`, scope `rotate` | New secret, same `key_id`. Returns `{key_id, secret}`. 409 if the key is not `ACTIVE` (revoked, or another rotate is in progress); no secret is issued. |
| `POST /keys/introspect` `{secret}` | none (the key is the credential) | 200 `{active: true, tenant_id, key_id, name}` or `{active: false}` (wrong secret, status not `ACTIVE`, malformed). 404 with no body if the prefix is unknown. |
| `GET /tenants/{tenant_id}/keys` | JWT `role` admin or member, scope `list` | Cursor-paginated list, see below. |
| `GET /health` | none | Liveness. |

## Key format

Raw key is `<prefix>.<secret>`. The secret is 256 bits from `secrets.token_urlsafe`. Only the
prefix and a SHA-256 hash of the secret are stored. Introspect looks up by prefix and compares
hashes with `hmac.compare_digest`. Each key records `created_by` (the creating admin's `uid`) and
`created_at` (UTC ISO timestamp).

## Listing keys (cursor pagination)

`GET /tenants/{tenant_id}/keys?limit=<n>&cursor=<c>` returns

```json
{"items": [{"key_id": "...", "name": "...", "prefix": "...", "status": "ACTIVE"}], "next_cursor": "..." }
```

Ordered by `name`, then `key_id` (names aren't unique). `limit` defaults to 20, allowed 1-50. `next_cursor` is
`null` on the last page; pass it back as `cursor` for the next one. A key created between page
requests is returned if it sorts after the cursor and is not revisited if it sorts before it. A `limit` outside 1-50 or not an integer, or a
malformed `cursor`, is a 400. The cursor is opaque (base64); treat it as a token.

## Key status

`status` is `ACTIVE`, `ROTATING` or `REVOKED`. Only `ACTIVE` introspects as active.

- **rotate:** claims the key with `UPDATE ... SET status='ROTATING' WHERE status='ACTIVE'`; exactly
  one concurrent caller wins, the rest get 409 and no secret. The winner then writes the new hash
  and sets `ACTIVE` with `WHERE status='ROTATING'`; if a revoke landed in between, that write
  matches nothing, the caller gets 409 and no secret, and the key stays `REVOKED`.
- **revoke:** sets `REVOKED` from any state. A revoked key stays revoked across rotate.

## Authentication and authorization

`Authorization: Bearer <JWT>`, HS256 (algorithm pinned), signed with the `JWT_SECRET` env var.
The app refuses to start without it. Required claims: `exp`, `aud`, `tid`, `role`, `uid`.
`aud` must be `api://keys`. `scope` is a space-separated string of endpoint scopes
(`create`, `revoke`, `rotate`, `list`).

- **401**: missing or non-Bearer header, bad signature, expired, wrong `aud`, missing claim,
  unknown `role`, unknown or mismatched `uid` (see below), or `tid` not equal to the `{tenant_id}` in the path.
- **403**: authenticated, but the role isn't allowed (a `member` on an admin endpoint) or the
  token lacks the endpoint's scope.
- **Users table:** the `uid` must exist in `users` (`uid`, `tenant_id`, `name`, `role`), its table
  role must equal the token's `role`, and its `tenant_id` must equal the token's `tid`. Any
  mismatch is a 401. Users are preseeded; there is no user API.
- Admins may call the member endpoints; members may not call admin endpoints.
- `POST /keys/introspect` and `GET /health` need no token.

## Known gaps

- A crash between the `ROTATING` claim and the final write leaves the key stuck in `ROTATING`
  (no recovery rule yet).
- No audit log yet (who rotated or revoked); only the creator is recorded.
- No `services` table; keys are not scoped to services.
- No dummy hash compare on an unknown prefix, so timing can reveal whether a prefix exists.

## Run

```bash
cd projects/04_api_key_vault
python -m pytest
JWT_SECRET=dev-secret-change-me-0123456789abcdef python run.py
```

## Try it with sample queries

There are no tenant or user endpoints, so seed tenants `t1`/`t2` and an admin and a member in each
(`uid` = `u-<role>-<tid>`). This creates `vault.db`; delete an old `vault.db` first, since the schema changed:

```bash
python scripts/seed.py
JWT_SECRET=dev-secret-change-me-0123456789abcdef python run.py   # leave running; use a second terminal for the calls below
```

Mint tokens in the second terminal (same `JWT_SECRET`):

```bash
export JWT_SECRET=dev-secret-change-me-0123456789abcdef
ADMIN=$(python scripts/make_token.py --tid t1 --role admin)
MEMBER=$(python scripts/make_token.py --tid t1 --role member --scope list)
ADMIN_T2=$(python scripts/make_token.py --tid t2 --role admin)
```

```bash
# 1. Create a key. The raw key in "secret" is shown only this once.
curl -s -X POST localhost:8000/tenants/t1/keys -H "Authorization: Bearer $ADMIN" \
  -H 'content-type: application/json' -d '{"name":"billing-worker"}'
# {"key_id":"key_...","secret":"gk_live_ab12.<secret>","prefix":"gk_live_ab12"}

# Copy the values from the response:
KEY_ID=key_...            # key_id
SECRET=gk_live_ab12....   # secret (the full prefix.secret string)

# 2. Introspect: active
curl -s -X POST localhost:8000/keys/introspect \
  -H 'content-type: application/json' -d "{\"secret\":\"$SECRET\"}"
# {"active":true,"tenant_id":"t1","key_id":"key_...","name":"billing-worker"}

# 3. List the tenant's keys as a member (add ?limit=2 and ?cursor=<next_cursor> to page)
curl -s localhost:8000/tenants/t1/keys -H "Authorization: Bearer $MEMBER"

# 4. Rotate: same key_id, new secret. The old secret goes inactive.
curl -s -X POST localhost:8000/tenants/t1/keys/$KEY_ID/rotate -H "Authorization: Bearer $ADMIN"
curl -s -X POST localhost:8000/keys/introspect \
  -H 'content-type: application/json' -d "{\"secret\":\"$SECRET\"}"
# {"active":false}

# 5. Revoke, then rotate again: 409, and the key stays revoked
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t1/keys/$KEY_ID/revoke -H "Authorization: Bearer $ADMIN"
# 204
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t1/keys/$KEY_ID/rotate -H "Authorization: Bearer $ADMIN"
# 409

# 6. Key under another tenant's admin: 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t2/keys/$KEY_ID/revoke -H "Authorization: Bearer $ADMIN_T2"
# 404

# 7. Authz failures
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t1/keys -H "Authorization: Bearer $MEMBER" \
  -H 'content-type: application/json' -d '{"name":"x"}'          # member on admin endpoint: 403
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/tenants/t1/keys                                   # no token: 401
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/tenants/t2/keys -H "Authorization: Bearer $ADMIN" # tid mismatch: 401
```
