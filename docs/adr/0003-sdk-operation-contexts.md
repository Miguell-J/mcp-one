# ADR 0003: Pooled HTTP with explicit SDK operation contexts

Status: accepted, 2026-09-10.

A persistent SDK context has task-group ownership and reconnection concerns; a
new HTTP client per call wastes connections. The high-level call_tool helper can
automatically run input-required rounds and implicitly list tools to validate
outputs. Neither behavior belongs implicitly in a gateway's retry policy.

Keep one bounded HTTP pool per configured server. Use public SDK Client contexts
per operation; adopt known modern discovery through the SDK. Call the public,
typed ClientSession.send_request with CallToolRequest and CallToolResult, without
hand-building JSON-RPC, framing or version negotiation. Validate output using the
captured catalog schema. Use public SDK x-mcp-header helpers for mirrored parameter
headers. Explicitly reject unsupported multi-round requests/results.

HTTP-level 401/403 and 5xx are classified in the bounded transport before the SDK
can reduce a non-RPC error body to generic INTERNAL_ERROR. Response bodies stay
opaque to this transport. Cookies are discarded at request/response hooks to
prevent connection reuse from introducing shared semantic sessions.

Consequences: one actual SDK tool invocation per attempt, no per-call rediscovery
for modern peers, no shared semantic session, and deterministic context cleanup.
Legacy fallback remains SDK-managed. Pin the SDK and keep real-client tests because
public low-level interfaces are less insulated from SDK evolution than conveniences.
