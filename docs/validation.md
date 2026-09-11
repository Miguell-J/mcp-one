# Native gateway validation

Executed 2026-09-11 on Linux x86_64. Python 3.14.3 on the development host;
Python 3.12.12 in the pinned Docker image. These results describe this candidate's
implementation, not the broken historical 0.1 branch.

| Check | Observed result |
| --- | --- |
| `make check` | Ruff and format clean; strict mypy, 25 source files; 62 tests passed |
| Coverage with real subprocesses | 91.28% combined branch/statement coverage; required 80% |
| Core coverage | Router 94%, registry 91%, circuit 97%, lifecycle 91% |
| Python 3.12 development container | 62 tests passed |
| Runtime/development Docker builds | Passed; runtime UID/GID 10001 |
| `uv build --no-sources` | Wheel and sdist built; no virtualenv, cache or secret file included |
| Scientific stack against native source | Full suite passed; direct/routed scientific contract comparison included |

The one warning is a third-party Starlette use of AnyIO's deprecated BlockingPortal
alias. No new deprecated MCP API is used. The local Docker host lacks buildx and
used its classic builder fallback; CI installs buildx explicitly.

The tests use real official SDK servers/clients over loopback HTTP. They cover
current discovery and headers, free SDK legacy handshake compatibility, schema and
result transparency, domain errors, failed discovery, malformed protocol, invalid
schemas/output, name collision, repeated pagination cursor, refused connection,
timeout, process death during execution, safe retry opt-in, circuit recovery,
metadata collisions, W3C trace ingress, cookie isolation, auth separation and
payload limits. Unit tests cover snapshots, partial readiness, automatic refresh,
admission, classification and cancellation. See adversarial-review.md.

Native stack E2E, pinned bootstrap, final remote CI and Codex registration evidence
are recorded by the companion mcp-stack docs/validation.md. That repository also
contains scripts/benchmark.py and the raw native-benchmark.json. Its local 100-call
smoke run observed direct median/p95 4.398/5.929 ms and gateway 10.314/14.949 ms:
about 5.916 ms extra median latency. This is not a load or scientific benchmark.

Reproduce standalone:

```bash
uv sync --locked
make check
make schema
uv build --no-sources
docker build --target runtime -t mcp-one:1.0.0rc1 .
docker build --target development -t mcp-one-tests:1.0.0rc1 .
docker run --rm --cap-drop ALL --security-opt no-new-privileges mcp-one-tests:1.0.0rc1
```

The proposed stable API has a breaking 1.0 migration, currently versioned
1.0.0rc1 for release review. No stable 1.0 release is implied by these development
tests. Public OAuth, distributed state, stdio, result caching, resource federation
and continuation workflows are outside this candidate's advertised scope.
