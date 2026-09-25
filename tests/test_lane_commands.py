"""Execute the Markdown recipes with a local argv-recording mock, never real Codex."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LANES = ("codex-implementer", "sol-implementer")
MODELS = dict(zip(LANES, ("gpt-6-luna", "gpt-6-sol")))
EFFORT_PLACEHOLDER = "<value from the spec's REASONING line, or empty>"


def blocks(lane: str) -> list[str]:
    text = (ROOT / "agents" / f"{lane}.md").read_text(encoding="utf-8")
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


def recipe(lane: str, phase: str, effort: str) -> str:
    examples = blocks(lane)
    if phase == "first":
        prepare, = [b for b in examples if "SPEC_FILES=()" in b]
        invoke, = [b for b in examples if "codex exec \\\n" in b]
        code = prepare + "\n" + invoke
    else:
        code, = [b for b in examples if "codex exec resume \\\n" in b]
    # Only spec/effort placeholders are substituted. Validation, array setup,
    # timeout, argv construction, rc handling and SID extraction are untouched.
    code = re.sub(
        r"\[Restate.*?\]", "OBJECTIVE: mock-only piece\nFILES: none\n"
        "INTERFACES: unchanged\nCONSTRAINTS: offline\nVERIFICATION: true"
        + (f"\nREASONING: {effort}" if effort else ""),
        code, flags=re.DOTALL,
    )
    return code.replace(EFFORT_PLACEHOLDER, effort)


@pytest.fixture(scope="module")
def bash() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        candidates = [Path(git).resolve().parent.parent / "bin/bash.exe"] if git else []
        candidates.append(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
        found = next((str(p) for p in candidates if p.is_file()), None)
    else:
        found = shutil.which("bash")
    if not found:
        pytest.skip("Bash (Git Bash on Windows) is required for Markdown execution tests")
    return found


@pytest.fixture
def runner(tmp_path: Path, bash: str):
    workspace = tmp_path / "lane workspace"
    mock_dir = workspace / "mock-bin"
    mock_dir.mkdir(parents=True)
    (workspace / "artifacts").mkdir()
    mock = mock_dir / "codex"
    mock.write_text(
        '#!/bin/bash\n'
        'printf "%s\\0" "$@" >> "$MOCK_ARGV"\n'
        'printf "\\0" >> "$MOCK_ARGV"\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--output-last-message" ]; then\n'
        '    printf "mock final\\n" > "$2"\n'
        '  fi\n'
        '  shift\n'
        'done\n'
        'cat > /dev/null\n'
        "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"mock-thread\"}'\n",
        encoding="utf-8", newline="\n",
    )
    mock.chmod(0o755)
    env = os.environ.copy()
    for key in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS"):
        env.pop(key, None)
    env["BASH_MAX_TIMEOUT_MS"] = "600000"

    def run(code: str) -> subprocess.CompletedProcess[str]:
        # PATH cannot resolve the user's authenticated Codex installation.
        setup = (
            'export PATH="$PWD/mock-bin:/usr/bin:/bin"\n'
            'export TMPDIR="$PWD/artifacts" MOCK_ARGV="$PWD/argv.bin"\n'
            '[ "$(command -v codex)" = "$PWD/mock-bin/codex" ] || exit 99\n'
        )
        return subprocess.run(
            [bash, "--noprofile", "--norc"], input=setup + code,
            cwd=workspace, env=env, capture_output=True, encoding="utf-8",
            errors="replace", timeout=20, check=False,
        )

    def calls() -> list[list[str]]:
        trace = workspace / "argv.bin"
        if not trace.exists():
            return []
        return [
            record.decode("utf-8").split("\0")
            for record in trace.read_bytes().split(b"\0\0") if record
        ]

    return run, calls


def assert_call(argv: list[str], lane: str, phase: str, effort: str) -> None:
    assert argv[:2] == (["exec", "resume"] if phase == "resume" else ["exec", "--model"])
    assert argv.count("--model") == 1
    assert argv[argv.index("--model") + 1] == MODELS[lane]
    overrides = [a for a in argv if a.startswith("model_reasoning_effort=")]
    assert overrides == ([f"model_reasoning_effort={effort}"] if effort else [])
    assert argv.count("-c") == bool(effort)
    if effort:
        assert argv[argv.index("-c") + 1] == overrides[0]
    assert "--json" in argv
    assert "--output-last-message" in argv
    if phase == "resume":
        assert "--sandbox" not in argv
        assert "--cd" not in argv
        assert argv[-2:] == ["mock-thread", "-"]
    else:
        assert argv[argv.index("--sandbox") + 1] == "workspace-write"
        assert "--cd" in argv
        assert "--skip-git-repo-check" in argv


@pytest.mark.parametrize("lane,next_effort", [(LANES[0], "low"), (LANES[0], ""), (LANES[1], "low")])
@pytest.mark.parametrize("fresh_shell", [False, True])
def test_resume_uses_only_current_effort(runner, lane: str, next_effort: str, fresh_shell: bool) -> None:
    run, calls = runner
    first = recipe(lane, "first", "high")
    resume = recipe(lane, "resume", next_effort)
    if fresh_shell:
        result = run(first + '\ndeclare -p SID SPEC_FILES DIAGNOSTIC_FILES > state.sh\n')
        assert result.returncode == 0, result.stdout + result.stderr
        # Restore only the documented SID and prior absolute artifact paths.
        # No EFFORT, EFFORT_ARGS, TIMEOUT_ARGS or CAP survives this shell.
        result = run('source ./state.sh\n' + resume)
    else:
        result = run(first + "\n" + resume)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls()) == 2
    assert_call(calls()[0], lane, "first", "high")
    assert_call(calls()[1], lane, "resume", next_effort)
    finals = [argv[argv.index("--output-last-message") + 1] for argv in calls()]
    assert finals[0] != finals[1]


@pytest.mark.parametrize("lane,effort", [(LANES[0], "ultra"), (LANES[0], "invalid"), (LANES[1], "invalid")])
@pytest.mark.parametrize("phase", ["first", "resume"])
def test_invalid_effort_is_refused_before_codex(runner, lane: str, effort: str, phase: str) -> None:
    run, calls = runner
    prefix = ""
    if phase == "resume":
        result = run(recipe(lane, "first", "high") + '\ndeclare -p SID SPEC_FILES DIAGNOSTIC_FILES > state.sh\n')
        assert result.returncode == 0, result.stdout + result.stderr
        prefix = 'source ./state.sh\n'
    previous = calls()
    result = run(prefix + recipe(lane, phase, effort))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED: effort {effort}" in result.stdout
    assert MODELS[lane] in result.stdout
    assert calls() == previous


@pytest.mark.parametrize("phase", ["first", "resume"])
def test_sol_accepts_ultra(runner, phase: str) -> None:
    run, calls = runner
    prefix = recipe(LANES[1], "first", "high") + "\n" if phase == "resume" else ""
    result = run(prefix + recipe(LANES[1], phase, "ultra"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert_call(calls()[-1], LANES[1], phase, "ultra")


@pytest.mark.parametrize("lane", LANES)
def test_all_documented_bash_blocks_parse(bash: str, lane: str) -> None:
    examples = blocks(lane)
    assert len(examples) >= 5
    for index, code in enumerate(examples):
        result = subprocess.run(
            [bash, "--noprofile", "--norc", "-n"], input=code,
            capture_output=True, encoding="utf-8", timeout=10, check=False,
        )
        assert result.returncode == 0, f"{lane} block {index}: {result.stderr}"


@pytest.mark.parametrize("lane", LANES)
@pytest.mark.parametrize("status", ["complete", "partial", "timeout", "unavailable", "refused"])
def test_existing_artifact_policy_for_two_pieces(runner, lane: str, status: str) -> None:
    run, calls = runner
    cleanup, = [b for b in blocks(lane) if 'STATUS="<final report status>"' in b]
    assertions = '\nfor file in "${SPEC_FILES[@]}"; do [ ! -e "$file" ] || exit 91; done\n'
    test = "! -e" if status == "complete" else "-s"
    assertions += f'for file in "${{DIAGNOSTIC_FILES[@]}}"; do [ {test} "$file" ] || exit 92; done\n'
    result = run(
        recipe(lane, "first", "high") + "\n" + recipe(lane, "resume", "low")
        + "\n" + cleanup.replace("<final report status>", status) + assertions,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls()) == 2
    assert "ARTIFACTS: none" in result.stdout if status == "complete" else "ARTIFACTS: /" in result.stdout
