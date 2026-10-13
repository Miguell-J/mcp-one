# Inspector development workflow

The official `@modelcontextprotocol/inspector` **2.10.1** is pinned with integrity
hashes in `tooling/package-lock.json`. Node >=22.22 is required. It is not installed
in Python runtime images and does not change the gateway protocol or configuration.

```bash
make tooling                 # npm ci --ignore-scripts --prefix tooling
make test-inspector          # real local downstream and gateway, no browser
```

The CLI tests require modern MCP 2026-07-28, compare direct/routed schemas, validate
structured output, check opaque metadata, domain `isError` and invalid arguments.
The Inspector's actual exit statuses are asserted, including code 5 for tool
errors. These checks demonstrate cross-SDK interoperability, not complete MCP
conformance. Python SDK contract, fault and E2E suites remain authoritative too.

For an existing operator-controlled, non-sensitive endpoint:

```bash
MCP_INSPECTOR_SECRET_STORE=memory \
MCP_STORAGE_DIR="$PWD/tooling/.inspector" \
MCP_INSPECTOR_OAUTH_STATE_PATH="$PWD/tooling/.inspector/oauth.json" \
  tooling/node_modules/.bin/mcp-inspector --cli --transport http \
  --server-url http://127.0.0.1:8000/mcp --protocol-era modern \
  --connect-timeout 5000 --method tools/list --strict --format json
```

Only invoke tools whose effects you understand and are authorized to perform.
`tools/call --tool-name NAME --tool-args-json '{...}'` sends native typed arguments;
inspect `outputSchema`, `structuredContent`, `isError` and `_meta`. Avoid recording
sensitive tool output. A failed command must retain its exit status: parsing stdout
must not turn an error into a passing check. Bound the enclosing subprocess too.

The web UI is optional and has broader secret/OAuth storage behavior. This workflow
uses the CLI with in-memory secrets and temporary test storage; it does not start a
browser proxy, persist credentials or modify `~/.codex/config.toml`. Inspector does
not replace the official SDK and must not be placed on the production call path.

Source documentation inspected on 2026-10-13:
- https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md
- https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md
- https://github.com/modelcontextprotocol/inspector/blob/main/docs/environment-variables.md
