# Working on MCP One

- MCP One is infrastructure only. Never put domain logic here.
- Native MCP is the primary protocol, using public official SDK interfaces.
- Never degrade downstream schemas, content, structuredContent, isError or _meta.
- Never retry mutating tools blindly. Annotations alone do not authorize retries.
- Never open infrastructure circuits on domain errors or caller validation errors.
- Never log secrets, headers or payload bodies by default.
- All routing changes require tests; protocol changes require real SDK contract/E2E tests.
- Architecture changes require an ADR and updated operational documentation.
- Use uv and the committed lock, Ruff and strict mypy. Python 3.12–3.14.
- Keep registry snapshots consistent during refresh. Close clients and cancel background work.
- Configuration is trusted operator input. Do not add remote configuration mutation.
- Run `make check` and real HTTP tests before committing. Report unexecuted checks honestly.
