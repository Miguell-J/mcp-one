---
name: mcp-protocol-audit
description: Audit native MCP discovery, input/output schemas, result fields and error compatibility when a gateway or adapter changes.
---

# mcp-protocol-audit

Run from this repository root. Read AGENTS.md and [native architecture](../../../docs/architecture.md). Use the official SDK; preserve content, structuredContent, isError and _meta.

1. Run `make test-contract test-e2e` for real Python SDK/HTTP behavior.
2. For cross-SDK checks, install `make tooling` then run `make test-inspector`. Node >=22.22 is required; this CLI test uses only local fixtures and in-memory secret storage.
3. Compare discovered schemas and results before/after routing; test valid arguments, invalid arguments, domain isError, protocol failures and metadata collisions separately.
4. Report negotiated protocol, SDK versions, executed cases, exit status and omissions. Inspector smoke tests do not prove complete protocol conformance.

See [Inspector procedure](../../../docs/inspector.md); avoid headers with credentials in shell history and never change global Codex configuration.
