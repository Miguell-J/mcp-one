# ADR 0001: Native MCP at both boundaries

Status: accepted, 2026-09-10.

The 0.1 core used REST tool maps and required two compatibility adapters in
mcp-stack. It lost schemas/results and did not implement native discovery.

Replace the old app package with a domain-independent MCP gateway. Use official
Python SDK 2.2.0 Server and Client for MCP 2026-07-28 on Streamable HTTP. REST
serves administration only, and legacy execution paths become migration notices.
No science package is imported. Advertise only supported tools capabilities.

Consequences: a breaking migration and a proposed 1.0 native contract. The stack
can remove both temporary adapters. Resources, subscriptions and multi-round
workflows are deferred, rather than implicitly promised by discovery.

Sources: https://modelcontextprotocol.io/specification/2026-07-28 and
https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0.
