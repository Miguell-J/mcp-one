# Security and threat model

Default deployment serves trusted local clients and trusted operator-enrolled MCP
servers. The threat boundary includes hostile browser origins, unauthenticated
local requests, oversized messages and broken downstream contracts. Operators and
installed downstream code are trusted; arbitrary hostile code and exponential
schema validation are not isolated by this process.

The listener binds loopback by default. SDK Host/Origin validation protects both
MCP and administrative HTTP. No wildcard CORS is enabled. The Docker image runs
uid/gid 10001; supplied Compose drops all capabilities, uses read-only source,
bounded temporary storage and no privileged/socket/host-home mounts.

Local bearer authentication is configured separately for `/mcp` and administrative
routes, via environment names only. Missing configured secrets fail closed. Tokens
are compared in constant time. `/health` and `/ready` are unauthenticated minimal
probes (Host/Origin protection still applies). Admin and upstream credentials are
not interchangeable unless the operator deliberately uses the same value. This
is a local shared-secret gate, not an OAuth implementation. Internet exposure
requires HTTPS and the SDK's OAuth resource-server facilities with proper audience,
issuer and scope policy; no full public OAuth claim is made by this MVP.

Downstream credentials are read from their own named environment variable, never
forwarded from the incoming Authorization header. HTTP cookies are discarded so
pooled connections cannot create implicit sessions shared between callers.
No inline YAML secret, token in
URL, ambient proxy or redirect is allowed. Config URLs are trusted operator input;
there is no dynamic URL tool argument, enrollment API or remote config mutation.
Secrets and payloads are omitted from logs; raw SDK exception logging is suppressed
at the executable boundary, and sanitized stable error codes are reported instead.

Messages, streamed responses, catalog/schema bytes and schema depth are bounded.
Compressed downstream responses are rejected before decompression. Non-local schema
references and base URI changes are rejected; JSON Schema validation uses a closed
reference registry and never fetches data. Valid local references and 2020-12
schemas are retained. Enrollment of CPU-hostile regex/recursive schemas is outside
the trusted-catalog model; use process isolation before accepting arbitrary catalogs.

A process-local active-call cap rejects overload; it is not a distributed rate
limiter. No user identifiers or payload values become metric labels. Artifact URIs
are opaque references and never authorize downloads. Do not turn on HTTP/SDK debug
payload logging for production traffic. Environment changes for upstream secrets
require restart; downstream secret values are read per operation.
