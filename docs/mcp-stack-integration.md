# Integration with mcp-stack

MCP One has no dependency on scientific_mcp_contracts. The scientific stack owns
its contracts, manifests, example adapter and scientific fixture. MCP One only
interprets servers, tools, schemas, policy and infrastructure status.

The new topology is Codex/SDK client -> MCP One /mcp -> mock-scientific-mcp /mcp.
Neither gateway-edge nor legacy-bridge belongs in the normal path. Stack manifests
render into native MCP One configuration. The hub's own Dockerfile builds from the
clean official dependency checkout, fixed by full SHA; the stack does not copy
or monkeypatch registry/router implementation.

Validate in mcp-stack with make bootstrap, make render, make lint, make test,
make test-contract, make test-template, make test-integration, make test-e2e,
make up, make health and make tools. Then point STACK_ENDPOINT at the published
Compose /mcp URL for the same real SDK E2E. Tests compare direct and routed
identity_matrix, contract_error and artifact results, including full content,
structuredContent, diagnostics, provenance, isError, original _meta and schemas.
The gateway preserves resource links and artifact checksums/URIs but does not
resolve them or advertise resource federation.

During upstream development only, the stack's subprocess test fixture accepts
MCP_ONE_SOURCE pointing at an isolated source checkout with its own locked virtual
environment. This does not alter bootstrap pins or production builds. Before
release, rerun against the actual clean pinned .deps checkout and Compose image.
