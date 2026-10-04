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
