"""Keep customer documentation free of private release and operator material."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")), *sorted((ROOT / "docs").rglob("*.json"))]
PRIVATE = re.compile(
    r"/Users/|/Volumes/|\.ts\.net\b|apps/api|"
    r"NOVABODY/[\w-]+(?:(?:/(?:pull|issues))|(?:#\d+))|(?:API|PR)\s*#\d+|"
    r"nova[-_](?:cli[-_])?internal\b|\b[0-9a-f]{40}\b|"
    r"(?:private|internal) (?:operator|package|repository|client)|"
    r"(?<![\w-])[\w.+-]+@(?![\w.-]*example\.(?:com|net|org|test)\b)[\w.-]+\.[a-z]{2,}",
    re.IGNORECASE,
)


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_customer_document_has_no_private_operational_material(document):
    match = PRIVATE.search(document.read_text())
    assert match is None, f"{document.relative_to(ROOT)} exposes private material: {match.group(0)}"


def test_command_reference_matches_offline_customer_discovery(capsys):
    import json

    from nova_cli_public import cli
    assert cli.main(["capabilities", "--json"]) == 0
    commands = json.loads(capsys.readouterr().out)["commands"]
    documented = {row[0]: row[1:] for row in re.findall(
        r"^\| `nova ([^`]+)` \| (.*?) \| (.*?) \| (.*?) \|$",
        (ROOT / "docs/Commands.md").read_text(), re.MULTILINE)}
    expected = {row["command"]: (
        "`" + row["mcp_tool"] + "`" if row.get("mcp_tool") else "CLI setup",
        ", ".join(row["effects"]),
        "`" + row["required_scope"] + "`" if row.get("required_scope") else "None",
    ) for row in commands}
    assert documented == expected, "Refresh command names, effects and scopes from capability discovery"


EXAMPLES = [(str(path.relative_to(ROOT)), line)
            for path in DOCUMENTS if path.suffix == ".md"
            for block in re.findall(r"```(?:sh|bash)\n(.*?)```", path.read_text(), re.DOTALL)
            for line in block.splitlines() if line.startswith("nova ")]


@pytest.mark.parametrize("document,command", EXAMPLES)
def test_published_cli_example_is_valid_input(document, command):
    import shlex

    from nova_cli_public.cli import build_parser
    try:
        build_parser().parse_args(shlex.split(command)[1:])
    except SystemExit as result:
        assert result.code == 0, f"Invalid command example in {document}: {command}"
