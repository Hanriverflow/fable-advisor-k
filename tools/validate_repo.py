#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run tools/validate_repo.py [REPOSITORY]
# 3. Or make executable and run:
#      chmod +x tools/validate_repo.py && ./tools/validate_repo.py [REPOSITORY]
# ──────────────────

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias, TypedDict

Fields: TypeAlias = dict[str, str]

PLUGIN_PATH: Final = ".claude-plugin/plugin.json"
MARKETPLACE_PATH: Final = ".claude-plugin/marketplace.json"
STATUS_VALUES: Final = frozenset(
    {"complete", "partial", "timeout", "unavailable", "refused"},
)
FRONT_MATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---\s*\n(.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)
EFFORT_ARM_RE: Final[re.Pattern[str]] = re.compile(
    r'case "\$EFFORT" in\s*\n\s*([^)\n]+)\)\s*;;',
)
STATUS_RE: Final[re.Pattern[str]] = re.compile(
    r"STATUS:\s*([a-z]+(?:\s*\|\s*[a-z]+)+)",
)
BASH_BLOCK_RE: Final[re.Pattern[str]] = re.compile(r"```bash\n(.*?)```", re.DOTALL)


@dataclass(frozen=True, slots=True, order=True)
class Finding:
    code: str
    path: str
    token: str


@dataclass(frozen=True, slots=True)
class DocumentContract:
    path: str
    name: str
    model: str | None
    bash_access: bool | None


@dataclass(frozen=True, slots=True)
class LaneContract:
    path: str
    model: str
    efforts: frozenset[str]


class FindingPayload(TypedDict):
    code: str
    path: str
    token: str


class ResultPayload(TypedDict):
    ok: bool
    findings: list[FindingPayload]


DOCUMENTS: Final = (
    DocumentContract("agents/fable-advisor.md", "fable-advisor", "fable", False),
    DocumentContract("agents/codex-implementer.md", "codex-implementer", "sonnet", True),
    DocumentContract("agents/sol-implementer.md", "sol-implementer", "sonnet", True),
    DocumentContract("skills/orchestration/SKILL.md", "orchestration", None, None),
)
LUNA_EFFORTS: Final = frozenset({"", "low", "medium", "high", "xhigh", "max"})
SOL_EFFORTS: Final = LUNA_EFFORTS | {"ultra"}
LANES: Final = (
    LaneContract("agents/codex-implementer.md", "gpt-6-luna", LUNA_EFFORTS),
    LaneContract("agents/sol-implementer.md", "gpt-6-sol", SOL_EFFORTS),
)
TIMEOUT_TOKENS: Final = (
    "BASH_MAX_TIMEOUT_MS",
    "-k 10",
    "CAP_MS / 1000 - 60",
    "-eq 124",
    "-eq 137",
)
RESUME_TOKENS: Final = ("codex exec resume", "thread.started", "thread_id", "resume --last")
TEMP_TOKENS: Final = ("SPEC=$(mktemp", "FINAL=$(mktemp", "LOG=$(mktemp")


def _read_text(root: Path, relative: str) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeError):
        return None


def _normalize_json(root: Path, relative: str, findings: list[Finding]) -> str | None:
    text = _read_text(root, relative)
    if text is None:
        findings.append(Finding("JSON_PARSE", relative, "json"))
        return None
    try:
        return json.dumps(json.loads(text), separators=(",", ":"), sort_keys=True)
    except json.JSONDecodeError:
        findings.append(Finding("JSON_PARSE", relative, "json"))
        return None


def _front_matter(text: str) -> Fields | None:
    matched = FRONT_MATTER_RE.search(text)
    if matched is None:
        return None
    fields: Fields = {}
    for line in matched.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        fields[key.strip()] = value.strip()
    return fields


def _check_json(root: Path, findings: list[Finding]) -> str | None:
    plugin = _normalize_json(root, PLUGIN_PATH, findings)
    marketplace = _normalize_json(root, MARKETPLACE_PATH, findings)
    version: str | None = None
    if plugin is not None:
        if '"name":"fable-advisor"' not in plugin:
            findings.append(Finding("JSON_KEY", PLUGIN_PATH, "name"))
        version_match = re.search(r'"version":"(\d+\.\d+\.\d+)"', plugin)
        if version_match is not None:
            version = version_match.group(1)
        else:
            findings.append(Finding("JSON_KEY", PLUGIN_PATH, "version"))
    if marketplace is not None:
        if '"name":"fable-advisor-k"' not in marketplace:
            findings.append(Finding("JSON_KEY", MARKETPLACE_PATH, "name"))
        if '"plugins":[{' not in marketplace:
            findings.append(Finding("JSON_KEY", MARKETPLACE_PATH, "plugins"))
        else:
            plugin_list = marketplace.split('"plugins":[', maxsplit=1)[1]
            if '"name":"fable-advisor"' not in plugin_list:
                findings.append(Finding("JSON_KEY", MARKETPLACE_PATH, "name"))
            if '"source":"./"' not in plugin_list:
                findings.append(Finding("JSON_KEY", MARKETPLACE_PATH, "source"))
    return version


def _check_documents(root: Path, findings: list[Finding]) -> None:
    for contract in DOCUMENTS:
        text = _read_text(root, contract.path)
        fields = None if text is None else _front_matter(text)
        if fields is None:
            findings.append(Finding("FRONT_MATTER", contract.path, "---"))
            continue
        if fields.get("name") != contract.name:
            findings.append(Finding("FRONT_MATTER", contract.path, "name"))
        if not fields.get("description"):
            findings.append(Finding("FRONT_MATTER", contract.path, "description"))
        if contract.model is not None and fields.get("model") != contract.model:
            findings.append(Finding("FRONT_MATTER", contract.path, "model"))
        if contract.bash_access is not None:
            tools = fields.get("tools", "")
            if not tools:
                findings.append(Finding("FRONT_MATTER", contract.path, "tools"))
            elif contract.bash_access != ("Bash" in tools):
                findings.append(Finding("FRONT_MATTER", contract.path, "Bash"))


def _check_lane(root: Path, findings: list[Finding], contract: LaneContract) -> None:
    text = _read_text(root, contract.path)
    if text is None:
        return
    bash_blocks = [matched.group(1) for matched in BASH_BLOCK_RE.finditer(text)]
    first_run_blocks = [
        block
        for block in bash_blocks
        if "codex exec" in block and "codex exec resume" not in block
    ]
    resume_blocks = [block for block in bash_blocks if "codex exec resume" in block]
    model_token = f"--model {contract.model}"
    if not first_run_blocks or model_token not in first_run_blocks[0]:
        findings.append(Finding("MODEL", contract.path, contract.model))
    if not resume_blocks or model_token not in resume_blocks[0]:
        findings.append(Finding("MODEL", contract.path, contract.model))
    if "REASONING:" not in text:
        findings.append(Finding("EFFORT", contract.path, "REASONING:"))
    effort_arm = EFFORT_ARM_RE.search(text)
    if effort_arm is None:
        findings.append(Finding("EFFORT", contract.path, "case"))
    else:
        efforts = frozenset(part.strip().strip('"') for part in effort_arm.group(1).split("|"))
        if efforts != contract.efforts:
            findings.append(Finding("EFFORT", contract.path, "ultra"))
    status_match = STATUS_RE.search(text)
    if status_match is None:
        findings.append(Finding("STATUS", contract.path, "STATUS"))
    else:
        statuses = frozenset(part.strip() for part in status_match.group(1).split("|"))
        for missing in sorted(STATUS_VALUES - statuses):
            findings.append(Finding("STATUS", contract.path, missing))
        for extra in sorted(statuses - STATUS_VALUES):
            findings.append(Finding("STATUS", contract.path, extra))
    for token in TIMEOUT_TOKENS:
        if token not in text:
            findings.append(Finding("TIMEOUT", contract.path, token))
    for token in RESUME_TOKENS:
        if token not in text:
            findings.append(Finding("RESUME", contract.path, token))
    if not resume_blocks:
        findings.append(Finding("RESUME", contract.path, "code-block"))
    else:
        resume_block = resume_blocks[0]
        for forbidden in ("--sandbox", "--cd"):
            if forbidden in resume_block:
                findings.append(Finding("RESUME", contract.path, forbidden))
        if 'cat > "$SPEC"' not in resume_block or "REASONING:" not in resume_block:
            findings.append(Finding("RESUME", contract.path, "spec"))
    if not all(token in text for token in TEMP_TOKENS):
        findings.append(Finding("TEMP_CREATE", contract.path, "mktemp"))
    sequence_is_complete = (
        "SPEC_FILES=()" in text
        and "DIAGNOSTIC_FILES=()" in text
        and text.count('SPEC_FILES+=("$SPEC")') >= 2
        and text.count('DIAGNOSTIC_FILES+=("$FINAL" "$LOG")') >= 2
    )
    if not sequence_is_complete:
        findings.append(Finding("TEMP_CLEANUP", contract.path, "sequence"))
    cleanup_is_complete = (
        '[ "$STATUS" = "complete" ]' in text
        and 'rm -f "${SPEC_FILES[@]}" "${DIAGNOSTIC_FILES[@]}"' in text
        and text.count('rm -f "${SPEC_FILES[@]}"') >= 2
    )
    if not cleanup_is_complete:
        findings.append(Finding("TEMP_CLEANUP", contract.path, "complete"))
    retain_tokens = ("ARTIFACTS:", "printf 'ARTIFACTS:'", '"${DIAGNOSTIC_FILES[@]}"')
    if not all(token in text for token in retain_tokens):
        findings.append(Finding("TEMP_RETAIN", contract.path, "ARTIFACTS:"))
    if "REFUSED:" not in text:
        findings.append(Finding("UNSUPPORTED", contract.path, "refused"))


def validate(root: Path) -> list[Finding]:
    if not root.is_dir():
        return [Finding(code="BAD_REPO", path=root.as_posix(), token="path")]
    findings: list[Finding] = []
    version = _check_json(root, findings)
    patches = _read_text(root, "PATCHES-K.md")
    if version is not None and (patches is None or f"`{version}`" not in patches):
        findings.append(Finding("VERSION", "PATCHES-K.md", version))
    _check_documents(root, findings)
    agents = root / "agents"
    if agents.is_dir():
        for path in agents.glob("*.md"):
            if path.stem == "fable-implementer":
                findings.append(Finding("STALE_AGENT", path.relative_to(root).as_posix(), path.stem))
    skill = _read_text(root, "skills/orchestration/SKILL.md")
    if skill is not None and "REASONING:" not in skill:
        findings.append(Finding("EFFORT", "skills/orchestration/SKILL.md", "REASONING:"))
    for lane in LANES:
        _check_lane(root, findings, lane)
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["-h"], ["--help"]):
        print("usage: validate_repo.py [REPOSITORY]")
        return 0
    if len(arguments) > 1:
        print("usage: validate_repo.py [REPOSITORY]", file=sys.stderr)
        return 2
    root = Path(arguments[0]) if arguments else Path.cwd()
    findings = validate(root)
    payload: ResultPayload = {
        "ok": not findings,
        "findings": [
            {"code": item.code, "path": item.path, "token": item.token} for item in findings
        ],
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    if findings and findings[0].code == "BAD_REPO":
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
