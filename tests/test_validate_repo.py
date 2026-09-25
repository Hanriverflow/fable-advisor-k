from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
TOOLS_DIR: Final = REPO_ROOT / "tools"
VALIDATOR: Final = TOOLS_DIR / "validate_repo.py"

from tools.validate_repo import Finding, LANES, STATUS_RE, STATUS_VALUES, validate


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _lane_body(model: str, efforts: str) -> str:
    return f"""REASONING: <effort>
case "$EFFORT" in
  {efforts}) ;;
  *) echo "REFUSED: unsupported effort"; exit 2 ;;
esac
STATUS: complete | partial | timeout | unavailable | refused | blocked
BASH_MAX_TIMEOUT_MS
CAP=$(( CAP_MS / 1000 - 60 ))
timeout -k 10 "$CAP"
[ "$RC" -eq 124 ]
[ "$RC" -eq 137 ]
thread.started
thread_id
SPEC_FILES=()
DIAGNOSTIC_FILES=()
SPEC=$(mktemp -t spec.XXXXXX)
FINAL=$(mktemp -t final.XXXXXX)
LOG=$(mktemp -t log.XXXXXX)
SPEC_FILES+=("$SPEC")
DIAGNOSTIC_FILES+=("$FINAL" "$LOG")
```bash
codex exec --model {model} --sandbox workspace-write --cd .
```
```bash
SPEC_FILES+=("$SPEC")
DIAGNOSTIC_FILES+=("$FINAL" "$LOG")
cat > "$SPEC" << 'SPEC_EOF'
OBJECTIVE
FILES
INTERFACES
CONSTRAINTS
VERIFICATION
REASONING:
SPEC_EOF
codex exec resume --model {model} SID
```
resume --last
STATUS="<final report status>"
if [ "$STATUS" = "complete" ]; then
  rm -f "${{SPEC_FILES[@]}}" "${{DIAGNOSTIC_FILES[@]}}"
  echo "ARTIFACTS: none"
else
  rm -f "${{SPEC_FILES[@]}}"
  printf 'ARTIFACTS:'
  printf ' %s' "${{DIAGNOSTIC_FILES[@]}}"
  printf '\n'
fi
"""


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write(
        root / ".claude-plugin/plugin.json",
        '{"name":"fable-advisor","version":"5.0.1"}',
    )
    _write(
        root / ".claude-plugin/marketplace.json",
        '{"name":"fable-advisor-k","plugins":[{"name":"fable-advisor","source":"./"}]}',
    )
    _write(root / "PATCHES-K.md", "release `5.0.1`\n")
    _write(
        root / "agents/fable-advisor.md",
        "---\nname: fable-advisor\ndescription: changed freely\nmodel: fable\n"
        +
        "tools: Read, Grep, Glob\n---\n",
    )
    _write(
        root / "agents/codex-implementer.md",
        "---\nname: codex-implementer\ndescription: routine\nmodel: sonnet\n"
        +
        "tools: Bash, Read\n---\n"
        + _lane_body("gpt-6-luna", '""|low|medium|high|xhigh|max'),
    )
    _write(
        root / "agents/sol-implementer.md",
        "---\nname: sol-implementer\ndescription: hard\nmodel: sonnet\n"
        +
        "tools: Bash, Read\n---\n"
        + _lane_body("gpt-6-sol", '""|low|medium|high|xhigh|max|ultra'),
    )
    _write(
        root / "skills/orchestration/SKILL.md",
        "---\nname: orchestration\ndescription: routing\n---\nREASONING: <effort>\n",
    )
    return root


def _replace(path: Path, replacement: tuple[str, str]) -> None:
    old, new = replacement
    content = path.read_text(encoding="utf-8")
    _ = path.write_text(content.replace(old, new), encoding="utf-8")


def _replace_once(path: Path, replacement: tuple[str, str]) -> None:
    old, new = replacement
    content = path.read_text(encoding="utf-8")
    _ = path.write_text(content.replace(old, new, 1), encoding="utf-8")


def test_returns_no_findings_when_contract_is_valid(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    # When
    findings = validate(root)
    # Then
    assert findings == []


def test_cli_returns_success_when_contract_is_valid(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    # When
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )
    # Then
    assert result.returncode == 0
    actual = json.dumps(json.loads(result.stdout), sort_keys=True)
    expected = json.dumps({"ok": True, "findings": []}, sort_keys=True)
    assert actual == expected


def test_cli_returns_bad_repo_when_path_is_missing(tmp_path: Path) -> None:
    # Given
    missing = tmp_path / "missing"
    # When
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(missing)],
        capture_output=True,
        check=False,
        text=True,
    )
    payload = json.dumps(json.loads(result.stdout), sort_keys=True)
    # Then
    assert result.returncode == 2
    assert '"code": "BAD_REPO"' in payload
    assert '"token": "path"' in payload


def test_reports_json_parse_when_plugin_json_is_invalid(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    _write(root / ".claude-plugin/plugin.json", "{")
    # When
    findings = validate(root)
    # Then
    assert Finding("JSON_PARSE", ".claude-plugin/plugin.json", "json") in findings


def test_reports_version_when_release_is_missing(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    _write(root / "PATCHES-K.md", "no release\n")
    # When
    findings = validate(root)
    # Then
    assert Finding("VERSION", "PATCHES-K.md", "5.0.1") in findings


Mutation = tuple[str, str, str, str, str]
MUTATIONS: Final[tuple[Mutation, ...]] = (
    ("agents/codex-implementer.md", "model: sonnet", "", "FRONT_MATTER", "model"),
    ("agents/codex-implementer.md", "gpt-6-luna", "other", "MODEL", "gpt-6-luna"),
    ("agents/codex-implementer.md", "xhigh|max)", "xhigh|max|ultra)", "EFFORT", "ultra"),
    ("agents/sol-implementer.md", "|ultra)", ")", "EFFORT", "ultra"),
    ("agents/codex-implementer.md", " | refused", "", "STATUS", "refused"),
    ("agents/codex-implementer.md", " | blocked", "", "STATUS", "blocked"),
    ("agents/sol-implementer.md", " | blocked", "", "STATUS", "blocked"),
    ("agents/codex-implementer.md", " | blocked", " | blocked | mystery", "STATUS", "mystery"),
    ("agents/sol-implementer.md", " | blocked", " | blocked | mystery", "STATUS", "mystery"),
    ("agents/codex-implementer.md", '-eq 124', "-eq 123", "TIMEOUT", "-eq 124"),
    ("agents/codex-implementer.md", "resume --model", "resume --sandbox --model", "RESUME", "--sandbox"),
    ("agents/codex-implementer.md", "thread.started", "thread.start", "RESUME", "thread.started"),
    ("agents/codex-implementer.md", "LOG=$(mktemp", "LOG=$(other", "TEMP_CREATE", "mktemp"),
    (
        "agents/codex-implementer.md",
        'rm -f "${SPEC_FILES[@]}" "${DIAGNOSTIC_FILES[@]}"',
        "",
        "TEMP_CLEANUP",
        "complete",
    ),
    ("agents/codex-implementer.md", "ARTIFACTS:", "FILES:", "TEMP_RETAIN", "ARTIFACTS:"),
    ("agents/codex-implementer.md", "REFUSED:", "ERROR:", "UNSUPPORTED", "refused"),
)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_reports_finding_when_contract_token_changes(
    tmp_path: Path,
    mutation: Mutation,
) -> None:
    # Given
    root = _valid_repo(tmp_path)
    relative, old, new, code, token = mutation
    _replace(root / relative, (old, new))
    # When
    findings = validate(root)
    # Then
    assert Finding(code, relative, token) in findings


def test_reports_stale_agent_only_inside_active_agents(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    _write(root / "agents/fable-implementer.md", "---\nname: old\n---\n")
    _write(root / "README.md", "manual fallback: fable-implementer\n")
    # When
    findings = validate(root)
    # Then
    assert Finding(
        "STALE_AGENT",
        "agents/fable-implementer.md",
        "fable-implementer",
    ) in findings


def test_ignores_description_prose_when_contract_is_valid(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    _replace(root / "agents/fable-advisor.md", ("changed freely", "arbitrary prose"))
    # When
    findings = validate(root)
    # Then
    assert findings == []


def test_reports_model_when_first_run_model_drifts(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    lane = root / "agents/codex-implementer.md"
    _replace_once(
        lane,
        (
            "codex exec --model gpt-6-luna --sandbox",
            "codex exec --model wrong --sandbox",
        ),
    )
    # When
    findings = validate(root)
    # Then
    assert Finding("MODEL", "agents/codex-implementer.md", "gpt-6-luna") in findings


def test_reports_cleanup_when_success_predicate_drifts(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    lane = root / "agents/codex-implementer.md"
    _replace_once(lane, ('[ "$STATUS" = "complete" ]', '[ "$STATUS" = "never" ]'))
    # When
    findings = validate(root)
    # Then
    assert Finding("TEMP_CLEANUP", "agents/codex-implementer.md", "complete") in findings


def test_reports_cleanup_when_piece_tracking_is_removed(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    lane = root / "agents/codex-implementer.md"
    _replace_once(lane, ('DIAGNOSTIC_FILES+=("$FINAL" "$LOG")', ""))
    # When
    findings = validate(root)
    # Then
    assert Finding("TEMP_CLEANUP", "agents/codex-implementer.md", "sequence") in findings


def test_reports_resume_when_later_piece_spec_is_empty(tmp_path: Path) -> None:
    # Given
    root = _valid_repo(tmp_path)
    lane = root / "agents/codex-implementer.md"
    _replace_once(lane, ('cat > "$SPEC" << \'SPEC_EOF\'', "true"))
    # When
    findings = validate(root)
    # Then
    assert Finding("RESUME", "agents/codex-implementer.md", "spec") in findings


@pytest.mark.parametrize("lane", LANES)
def test_real_lane_accepts_all_six_statuses(lane) -> None:
    expected = {"complete", "partial", "timeout", "unavailable", "refused", "blocked"}
    text = (REPO_ROOT / lane.path).read_text(encoding="utf-8")
    match = STATUS_RE.search(text)
    assert match is not None
    assert {part.strip() for part in match.group(1).split("|")} == expected
    assert STATUS_VALUES == expected
    assert validate(REPO_ROOT) == []


def test_host_block_document_contract_is_consistent() -> None:
    # This checks written policy, not Claude Code's live permission system.
    policies = []
    for lane in LANES:
        text = (REPO_ROOT / lane.path).read_text(encoding="utf-8")
        policies.append(text.split("## Host permission blocks\n", 1)[1].split("## The contract", 1)[0])
        assert "For `blocked`, follow the preservation/reporting rule above; do not enter this cleanup recipe." in text
        assert "escalation requires explicit `REASONING` before invocation" in text
        assert "configured default" in text and "record the omission in `GAPS`" in text
        assert "Follow all applicable user and project instructions and security" in text
        assert "If an instruction conflict remains unresolved, stop and report it." in text
    assert policies[0] == policies[1]
    orchestration = (REPO_ROOT / "skills/orchestration/SKILL.md").read_text(encoding="utf-8")
    recovery = orchestration.split("Handle abnormal outcomes by cause:", 1)[1].split("## Choosing reasoning effort", 1)[0]
    for policy in [*policies, recovery]:
        for token in (
            "permission system", "auto-mode", "Codex execution", "creating/writing the task spec",
            "stop immediately", "STATUS: blocked", "observed denial", "blocked step", "GAPS",
            "prompt, preamble, flags, script, or execution path", "another lane",
            "inform the user", "explicit decision", "`permission` or `403`",
            "unavailable", "refused", "earlier pieces", "verified changes",
            "every existing temporary artifact, including specs", "absolute paths already recorded",
            "If no artifacts were created", "ARTIFACTS: none", "not started", "not run",
            "never invent a process exit code, log", "Do not issue further tool calls",
            "cleanup limitation",
        ):
            assert token in policy, token


def test_uses_standard_library_and_stays_under_size_limit() -> None:
    # Given
    source = VALIDATOR.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {
        "__future__",
        "dataclasses",
        "json",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
    # When
    imports = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    pure_lines = [
        line for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    # Then
    assert imports <= allowed
    assert len(pure_lines) <= 250
