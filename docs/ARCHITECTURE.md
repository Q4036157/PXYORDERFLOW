# Architecture

```text
Market data adapter
        |
        v
BookEngine + FlowEngine
        |
        +----> FastAPI / WebSocket ----> Vue UI
        |
        v
RiskOf ----> TradeClient ----> Mock or private execution adapter
```

Market data and execution are separate adapters. A slow UI consumer may lose
intermediate updates, but it must not block market-data ingestion or execution.

The public build includes Lighter public market data and an in-memory Mock
execution adapter. Production execution adapters must live behind server-side
authentication, tenant authorization, risk checks, and audit logging.

## Default ports

| Component | Address |
| --- | --- |
| Vue development server | `127.0.0.1:3810` |
| FastAPI and WebSocket | `127.0.0.1:3811` |

Services bind to loopback by default. Put authentication and TLS at a trusted
reverse proxy before exposing the application to a network.
