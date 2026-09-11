# Adversarial and operational review

Review performed after the native rewrite, 2026-09-11. The scope is a local,
operator-configured tools gateway, not an arbitrary-code security boundary.

| Risk | Resolution and evidence |
| --- | --- |
| Duplicate mutation after timeout/disconnect | No SDK high-level automatic rounds or transport retries; real fixture execution counters prove a single mutation on timeout and process death. |
| Annotation interpreted as retry authorization | Both configured original-name allowlist and read-only/idempotent annotation are required; real safe retry executes exactly twice. |
| Late success closes a newer open circuit | Epoch-tagged permits; unit tests cover stale completions and one half-open probe. |
| Domain/caller/auth error opens circuit | Native domain and input errors remain separate; HTTP 401/403 is classified before the SDK generic fallback; real auth test verifies CLOSED and readiness 503. |
| Refresh exposes partial catalogs | Build complete candidates, atomic immutable map swap; a concurrent reader retains the prior generation. |
| Collision or invalid replacement schema | Withdraw that server's candidate; other valid servers remain routable. Stale snapshots have explicit age bounds. |
| Implicit session through HTTP cookies | Discard cookies while retaining connection pooling; separate real SDK clients route successfully despite downstream Set-Cookie. |
| Lost trace parent | Extract HTTP W3C context with OpenTelemetry; SDK propagates MCP metadata. Real test verifies caller, gateway and downstream trace IDs match. |
| Metadata/schema loss | Direct-versus-aggregated Tool equality except name; native result content, structuredContent, isError and opaque metadata equality. Existing gateway namespace gets a separate hop key. |
| Payload/token logs | Safe codes instead of exception text; real auth test scans gateway logs for fixture token and payload. |
| Client/task leaks or shutdown hang | Operation contexts exit in their owner task; pooled clients close; supervisor is cancelled/awaited; telemetry exporter shuts down. Cancellation releases admission/probe slots. |
| Unsafe remote schema retrieval | Closed reference registry, no external references/base changes, bounded bytes/depth, compressed/redirect responses rejected. |

Remaining boundaries are documented in security.md: trusted catalogs can contain
CPU-expensive schema expressions; process isolation is needed for hostile catalogs.
Cancellation cannot undo a side effect already performed remotely. An infrastructure
timeout is an uncertain outcome, never proof that a mutation did not happen.
No result caching, distributed circuits, public OAuth, resources federation or
multi-round continuation execution is claimed.
