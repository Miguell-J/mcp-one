# Circuit breaker

Circuits are per configured server, local to the event loop and process. CLOSED
admits calls. Consecutive infrastructure failures reach failure_threshold and
transition to OPEN. After reset_seconds, exactly one caller acquires HALF_OPEN;
concurrent callers are rejected until that probe settles. Success or a legitimate
domain isError proves transport completion and closes the probe. Infrastructure
failure reopens it. Cancelled probes release the slot without recording a failure.
All timing uses monotonic time.

An epoch on each permit prevents delayed completions of calls admitted before an
opening from closing a newer circuit. Admission and settlement contain no awaits;
concurrent async calls cannot reserve the same probe. Discovery/probe refresh does
not clear the circuit. Administrative status reports OPEN/HALF_OPEN accurately;
readiness considers when an open circuit can accept a recovery probe.

Failures that count: timeout, refused/lost connections, 5xx/unavailability,
malformed MCP data and invalid runtime output against its declared schema.
Failures that do not count: native domain isError, caller input errors, policy or
capacity rejection, unknown tool, explicit auth rejection and caller-attributed
MCP errors. Errors are classified by type/code, never message matching.

Retries settle one circuit outcome per logical call; infrastructure metrics count
each failed attempt. A successful safe retry leaves the circuit closed. State
resets on process restart. Distributed circuits are not claimed.
