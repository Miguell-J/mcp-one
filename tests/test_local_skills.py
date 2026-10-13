"""Repository skill metadata and relative references must remain resolvable."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2 if "unit" in Path(__file__).parts else 1]
NAMES = ["gateway-resilience", "mcp-protocol-audit"]


@pytest.mark.parametrize("name", NAMES)
def test_local_skill_is_named_bounded_and_has_resolvable_references(name):
    folder = ROOT / ".agents/skills" / name
    document = (folder / "SKILL.md").read_text()
    assert document.startswith("---\n")
    frontmatter, body = document[4:].split("\n---\n", 1)
    assert re.search(rf"^name: {re.escape(name)}$", frontmatter, re.MULTILINE)
    assert re.search(r"^description: .{30,}$", frontmatter, re.MULTILINE)
    assert len(body.splitlines()) <= 60
    for reference in re.findall(r"\]\(([^)]+)\)", body):
        assert (folder / reference).is_file(), reference
    metadata = (folder / "agents/openai.yaml").read_text()
    assert "allow_implicit_invocation: false" in metadata
    assert f"${name}" in metadata
    commands = re.findall(r"`make ([^`]+)`", body)
    makefile = (ROOT / "Makefile").read_text()
    for command in commands:
        for target in command.split():
            if "=" not in target:
                assert re.search(rf"^{re.escape(target)}:", makefile, re.MULTILINE), target
