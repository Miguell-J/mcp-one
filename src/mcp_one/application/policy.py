from fnmatch import fnmatchcase

from mcp_one.config import PolicyConfig


class PolicyEngine:
    def __init__(self, config: PolicyConfig):
        self.config = config

    def permits(self, tool: str) -> bool:
        return any(fnmatchcase(tool, pattern) for pattern in self.config.allow) and not any(
            fnmatchcase(tool, pattern) for pattern in self.config.deny
        )
