# API key vault

Multi-tenant API key vault (FastAPI + SQLite). An admin creates API keys for machine
clients and gets the raw key back once; later introspect calls say whether a key is active.

## Endpoints

| Method & path | Audience | Purpose |
|---|---|---|
| `POST /tenants/{tenant_id}/keys` `{name}` | admin | Create a key. Returns `{key_id, secret, prefix}`; the raw key is shown once. |
| `POST /tenants/{tenant_id}/keys/{key_id}/revoke` | admin | Revoke. Idempotent; the next introspect is inactive. |
| `POST /tenants/{tenant_id}/keys/{key_id}/rotate` | admin | New secret, same `key_id`. Returns `{key_id, secret}`. 409 if the key is revoked. |
| `POST /keys/introspect` `{secret}` | member | Always 200: `{active: true, tenant_id, key_id, name}` or `{active: false}`. |
| `GET /tenants/{tenant_id}/keys` | member | List `key_id`, `name`, `prefix`, `revoked`. |
| `GET /health` | none | Liveness. |

## Key format

Raw key is `<prefix>.<secret>`. The secret is 256 bits from `secrets.token_urlsafe`. Only the
prefix and a SHA-256 hash of the secret are stored. Introspect looks up by prefix and compares
hashes with `hmac.compare_digest`. A revoked key stays revoked across rotate.

## Known gaps

- No authentication or admin/member role enforcement yet; the admin and member routes are open.
- No `users` or `services` tables; keys are not scoped to services.
- No dummy hash compare on an unknown prefix, so timing can reveal whether a prefix exists.

## Run

```bash
cd projects/04_api_key_vault
python -m pytest
python run.py
```

## Try it with sample queries

There is no tenant endpoint yet, so seed two tenants first (this creates `vault.db`):

```bash
python -c "
import sqlite3, app.db as d
c = sqlite3.connect(d.DB_PATH); d.init_db(c)
c.execute(\"INSERT OR IGNORE INTO tenants VALUES ('t1','Tenant 1'),('t2','Tenant 2')\"); c.commit()"
python run.py          # leave running; use a second terminal for the calls below
```

```bash
# 1. Create a key. The raw key in "secret" is shown only this once.
curl -s -X POST localhost:8000/tenants/t1/keys \
  -H 'content-type: application/json' -d '{"name":"billing-worker"}'
# {"key_id":"key_...","secret":"gk_live_ab12.<secret>","prefix":"gk_live_ab12"}

# Copy the values from the response:
KEY_ID=key_...            # key_id
SECRET=gk_live_ab12....   # secret (the full prefix.secret string)

# 2. Introspect: active
curl -s -X POST localhost:8000/keys/introspect \
  -H 'content-type: application/json' -d "{\"secret\":\"$SECRET\"}"
# {"active":true,"tenant_id":"t1","key_id":"key_...","name":"billing-worker"}

# 3. List the tenant's keys (hashes are never returned)
curl -s localhost:8000/tenants/t1/keys

# 4. Rotate: same key_id, new secret. The old secret goes inactive.
curl -s -X POST localhost:8000/tenants/t1/keys/$KEY_ID/rotate
curl -s -X POST localhost:8000/keys/introspect \
  -H 'content-type: application/json' -d "{\"secret\":\"$SECRET\"}"
# {"active":false}

# 5. Revoke, then rotate again: 409, and the key stays revoked
curl -s -X POST localhost:8000/tenants/t1/keys/$KEY_ID/revoke
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t1/keys/$KEY_ID/rotate
# 409

# 6. Wrong tenant: 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/tenants/t2/keys/$KEY_ID/revoke
# 404
```
