# ADR 0002: Atomic catalog snapshots and failure safety

Status: accepted, 2026-09-10.

Refreshing a live registry must not expose partial tools or silently overwrite
collisions. Validate a whole candidate server catalog, then publish a frozen
snapshot with read-only maps. Use explicit namespaces and preserve original names.
Retain stale definitions only during bounded transient outages; withdraw unsafe
replacement catalogs. Calls use the snapshot they captured at admission.

Retry tool calls only with explicit per-tool operator policy and safe annotations.
Keep discovery/probe retries independent. Use monotonic circuits, epoch permits
and one half-open probe. Never trip circuits on domain isError or caller errors.
Do not implement result caching in this release. Preserve all native result fields
and append metadata using an unoccupied gateway namespace key.

Consequences: predictable partial degradation and bounded recovery without a
second protocol, Redis or hidden session. Replica-local operational state is an
explicit limitation. Tests must cover races, stale catalogs, duplicates and retry
execution counts, not just HTTP success codes.
