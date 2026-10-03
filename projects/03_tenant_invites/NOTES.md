# Tenant invites notes

Built by pair-programming with Claude Code: I drove the decisions, the AI implemented and
flagged trade-offs. Built in thin slices, tests alongside each.

## Spec (as given)

- `POST /tenants/{tenant_id}/invites`: admin JWT, `tid` must equal the path. Builds the token;
  does not sign anyone up.
- `POST /invites/accept`: no JWT; the token in the body is the credential. Creates the member.
- `GET /tenants/{tenant_id}/members`: JWT for that tenant; member or admin may list.
- JWT: `Authorization: Bearer`, `aud=api://invites`, `tid` must match the path tenant.
- Token: at least 128 bits from a CSPRNG, compare the hash in constant time, 7-day default expiry.
- One pending invite per `(tenant_id, email)`; creating again returns the existing invite id and
  a new token and invalidates the old one.
- Accept must be safe under concurrency: one member, one 409.

## Decisions I made

- Token is `<invite_id>.<secret>`: lookup by indexed id, then `compare_digest` on the hash of the
  secret. 256-bit secret, only the SHA-256 stored.
- Re-issue keeps the invite id, rotates the secret (replacing the hash kills the old token) and
  resets expiry. Create returns 201 in both cases.
- Users are identified by email and can belong to many tenants; membership is unique per
  `(tenant, user)`.
- Accept claims the invite with one conditional `UPDATE ... WHERE used_at IS NULL AND expires_at > now`
  in the same transaction as user/member creation.
- Already a member: 409 with a message, nothing stored, invite stays unused.
- Used token (genuine secret): 409. Malformed/unknown/wrong/expired/replaced: one generic 400.
- Used invites are kept for audit (and so a replay can be told apart from a bad token).
- Listing members is open to both `member` and `admin`; creating is admin-only.

## Security notes

- `alg` pinned to HS256 (no `none`, no algorithm confusion); `exp`, `aud`, `sub`, `tid`, `role` required.
- Authn (401) before authz (403) before body validation. Wrong tenant and unknown tenant both 403.
- Unknown invite ids are verified against a dummy hash so the code path doesn't short-circuit.
- Server refuses to start without `JWT_SECRET`.

## Testing

Unit (tokens, services), API, auth matrix (11 bad-token variants on both protected endpoints),
and real-thread concurrency tests (10 racing accepts, one 201 and nine 409, over HTTP and at the
service level). I checked the race test fails when the `used_at IS NULL` guard is removed.

## Known gaps

- No token issuance, email sending, revocation/list of invites, or rate limiting on accept.
- Tenants aren't a table; no migrations (`create_all` at startup).
- Used/expired invites are never purged.
- Package is named `app` rather than following the `name/` convention.
