---
name: gateway-resilience
description: Validate gateway timeout, circuit, recovery, concurrency and cancellation behavior after changes to routing or lifecycle.
---

# gateway-resilience

Run from this repository root. Read [retry policy](../../../docs/retries.md) and [circuit policy](../../../docs/circuit-breaker.md).

1. Run `make test-fast` for deterministic admission/snapshot/cancellation checks.
2. Run `make test-integration` for actual HTTP outages, deadlines, recovery and pool cleanup.
3. Synchronize concurrency tests with events; inspect active calls returning to zero and one half-open probe. Distinguish logical calls from retry attempts.
4. Require exact attempt counts. Safe retries require operator enrollment plus a safe annotation; mutation, validation, domain errors and ambiguous outcomes do not grant retry authority.
5. Record metrics and circuit state at failure and recovery. Do not fault external services; use repository fixtures and always close processes/resources.

Finish with commands, counts and residual risks; do not replace assertions or widen permissions to make tests pass.
