# Retry safety

Discovery defaults to up to 3 attempts, health to 1, and tool execution to 1.
Only explicitly classified transient transport failures are retried, with bounded
linear backoff. Schema errors, auth rejection, caller errors and domain isError
never initiate automatic retries. Discovery and health have independent counters
and policies; neither executes tools or trips the tool circuit.

Tool retries require **both** the operator's exact downstream tool name in
`retry.safe_tools` and a readOnlyHint or idempotentHint from that enrolled server.
Annotations are advisory and never sufficient by themselves. Configure only tools
whose retry safety the operator has verified. Determinism is not inferred from
scientific output or provenance. There is no result cache.

```yaml
retry:
  call_attempts: 2
  safe_tools: [lookup]
  backoff_seconds: 0.2
```

`lookup` is the original downstream name, not necessarily the prefixed public name.
The attempt count measures actual downstream SDK calls. Validation, policy,
capacity and open-circuit rejections have zero attempts. A half-open circuit permits
one probe and never retries it. Cancellation releases admission and probe state.
A mutating tool with no explicit safety policy is never automatically called twice.
Timeouts and disconnects can leave an unknown execution outcome at the downstream;
MCP One cannot provide exactly-once semantics. Explicitly safe retries accept this
ambiguity. Each attempt has the configured call deadline; total time includes all
attempt deadlines plus backoff. Infrastructure failures are counted per attempt,
but a circuit failure is settled once per admitted logical gateway call.

The transport sets HTTP connection retries to zero. The SDK can resume a response
stream through its protocol transport; it does not confer authorization to replay
an application mutation. Multi-round tool workflows are explicitly outside scope.
