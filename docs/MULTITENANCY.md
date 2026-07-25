# Multi-tenancy

Tenant isolation is a server-side security boundary. A tenant or account ID
supplied by the browser is never sufficient authorization.

## Required request flow

1. A trusted identity service authenticates the user.
2. The API derives `tenant_id` and `user_id` from a verified session or token.
3. The execution gateway verifies the user's role and account membership.
4. Risk checks run against tenant, account, instrument, and daily limits.
5. The gateway writes an idempotent order request and immutable audit event.
6. Only then may an exchange adapter send the order.

## Isolation checklist

- Every account, order, fill, API credential, and audit record has `tenant_id`.
- Database policies reject cross-tenant reads and writes.
- Redis keys and WebSocket topics include the server-derived tenant ID.
- Exchange credentials are encrypted and never returned to the browser.
- `cancel_all` is scoped to one authorized account and explicit order source.
- Operators use audited, time-limited support access.
- Integration tests attempt cross-tenant account, order, and WebSocket access.

For small hosted deployments, a shared PostgreSQL database with row-level
security is a practical starting point. Dedicated deployments remain available
for customers who require stronger physical isolation.
