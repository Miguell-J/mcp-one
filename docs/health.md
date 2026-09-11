# Health, discovery and readiness

| State | Meaning |
| --- | --- |
| STARTING | Configured; initial discovery has not completed |
| ONLINE | Valid catalog discovered and MCP reachable |
| DEGRADED | Last known catalog retained during a transient outage, or last call/probe failed |
| OFFLINE | No usable catalog, expired catalog, or invalid replacement catalog |
| CIRCUIT_OPEN | Infrastructure failures temporarily block calls, including a half-open probe |
| UNKNOWN | Reserved for unavailable operational knowledge |

`GET /health` means the application lifespan is active. It is liveness, not an
assertion about downstreams. `GET /ready` is 200 only after registry initialization,
a running supervisor and at least minimum_ready_servers with an available permitted
tool and an admissible circuit. Otherwise it is 503. All servers need not be online.
`GET /status` separates catalog availability, stale/error state and circuit state.
No discovery/network traffic is triggered by GET health/ready/status/metrics.

Startup discovers each enabled server, paginates tools and validates the complete
candidate. Refresh runs periodically, or via POST /refresh, coalesced with a minimum
interval to avoid hammering. Transient transport failures retain the last valid
catalog for stale_seconds; invalid schemas/collisions withdraw that server's routes.
Other servers remain available. There are no cached tool results to serve offline.
Recovered discovery replaces the stale entry atomically. Health probes separately
use SDK server discovery, with their own timeout/retry/interval; they never reset
a tool circuit. A successful actual tool probe closes a half-open circuit.

Catalog cache is an operational routing snapshot. The gateway advertises private
TTL zero upstream, because its periodic snapshot can already be older than a
backend's freshness hint. Clients must not mistake stale operational metadata for
fresh downstream discovery. Downstream discovery hints/capabilities are retained
for diagnostics; operator refresh and stale budgets govern the local snapshot.
The successful catalog expires defensively even if background refresh stalls.
