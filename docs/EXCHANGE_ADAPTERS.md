# Exchange adapters

Execution integrations implement `TradeClient` from
`backend/app/trade/clients.py`.

An adapter must provide account discovery, limit-order placement, single-order
cancellation, scoped cancel-all, and open-order queries. It must also:

- preserve native quantity and price precision;
- create deterministic client order IDs for retries;
- map exchange states into the public order model;
- respect rate limits and bounded timeouts;
- avoid logging credentials, signatures, or complete private responses;
- enforce tenant and account authorization before sending an order.

Add new venue adapters behind a feature flag and include a Mock-backed contract
test. Do not commit API keys, private endpoints, production account IDs, or
captured private order payloads.
