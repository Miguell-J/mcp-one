# Routing and preservation

The public name is `namespace + '.' + downstream_name`, unless the downstream
name already starts with exactly that namespace and dot. Names are case sensitive,
ASCII letters/digits/underscore/hyphen/dot, at most 128 characters after prefixing.
`echo` and `demo.echo` both normalize to `demo.echo` under namespace demo; if both
appear, the entire candidate server catalog is rejected. No overwrite, random
suffix or discovery-order counter is permitted. Duplicate namespaces fail config
validation. `system.echo` under demo becomes `demo.system.echo`.

A ToolRoute separately records upstream_name, downstream_name, server_id and
namespace. Lookup is a dictionary index in an immutable catalog snapshot. The
original downstream name is sent on the native call; only the advertised name
changes. Description, title, schemas, annotations, icons and valid MCP metadata
remain SDK Tool fields, unchanged. MCP One does not require an outputSchema, but
preserves and validates it when a downstream advertises one.

Calls follow: route lookup, policy, bounded argument/schema validation, stale
catalog check, capacity admission, circuit admission, native call, result/schema
validation, metrics and namespaced metadata. Unknown tools are SDK MCPError -32602;
known-tool gateway failures use isError with a stable infrastructure/gateway code.
Domain results retain their native isError and arbitrary domain metadata.

`content`, `structuredContent`, `isError`, `_meta` and valid additional SDK fields
remain intact. No success/result/error administrative envelope replaces the result.
Successful outputSchema applies to successful structuredContent, not domain errors.
References in content or structured output are never downloaded or interpreted.

On success or domain error, the gateway adds
`io.github.miguell-j.mcp-one/gateway`. If that key already exists, it is retained
and this hop uses `/hop-1`, `/hop-2`, etc. No downstream key is overwritten.
The SDK owns reserved metadata, including its server identity stamp.

Policy uses case-sensitive glob allow/deny lists, with deny winning. It applies
both to listing and execution. There is one operator policy, not per-client RBAC.
Client-scoped authorization can later implement a richer PolicyEngine boundary.
