# ADR 0004: Independent development client and bounded admission telemetry

Status: accepted, 2026-10-13.

Existing Python SDK fault/contract tests cover gateway behavior, but cannot alone
establish interoperability with an independently implemented client. Use the
pinned official Inspector CLI as optional development tooling and a separate CI
job, including negative cases. Do not add it to runtime images or replace SDK tests.

Expose `mcp_one_active_calls{server=""}` for logical admission occupancy, including
safe retry/backoff time; rejected calls never increase occupancy. Return to zero
in `finally` after success, error or cancellation. Existing logical-call outcomes
count cancellation independently from infrastructure-attempt failures. Add stable
outcome/attempt attributes to route spans and emit the same bounded metadata event
on cancellation without input/output values. ProcessCollector reports process CPU,
RSS and file-descriptor signals on supported OSes, using the existing private
registry. These are process measurements, not whole-host/container accounting.

Alternative: scrape admission from logs or add another monitoring service. A gauge
is cheaper and reflects live occupancy. No scheduler, queue, distributed limit,
new retry, result cache, domain coupling or new Python dependency is introduced.
The scientific stack keeps its upstream pin: telemetry changes in this checkout
are validated separately until a reviewed upstream pin migration is requested.
