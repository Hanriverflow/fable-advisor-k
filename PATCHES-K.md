# fable-advisor-k — delta vs upstream

Fork of [DannyMac180/fable-advisor](https://github.com/DannyMac180/fable-advisor), carrying
task-sizing and timeout-hardening patches for the codex lane. Plugin name stays `fable-advisor`
so all skill/agent invocations (`/fable-advisor:orchestration`, `fable-advisor:codex-implementer`, …)
are identical to upstream; only the marketplace/repo identity is `-k`.

Tracks upstream through ad2bdc3 (2026-08-04: Luna repin + refusal detection). The refusal
patch is kept as-is; the repin is superseded by this fork's config-SOT policy below.

## Why (measured, 2026-07 / structured-finance repo)

A single `codex exec` under Claude Code's Bash tool dies at the tool's wall clock
(120 s default, 600 s stock maximum). A frontier GPT tier at high reasoning rabbit-holes
on bundled specs: the same task took 23.3 min (timeout kill, work lost) as one monolith
vs 8.1 min when decomposed with a STOP-scoped spec. Upstream v4 re-routes a timed-out
monolith to the Fable lane — the most expensive model — instead of splitting it.

## The patches

### v4.0.1 — task-sizing doctrine

`skills/orchestration/SKILL.md` (architect side):
- **"Task sizing — keep codex calls short"**: one deliverable per delegation (~5-minute
  pieces), chain instead of bundling, write-early-then-STOP spec tails.
- Re-route rule split: `unavailable` → fable-implementer with the same spec (upstream
  behavior); `timeout` → **split first**, re-delegate to codex, escalate only for
  judgment failures, not size.

`agents/codex-implementer.md` (lane side):
- **"Size the work — sequence anything big"**: sequential short `codex exec` calls,
  context carried between pieces via `codex exec resume <session-id>`.
- Inner shell timeout fires 60 s before the Bash tool's own kill, so timeouts get
  observed and reported (`STATUS: timeout` + partial work on disk) instead of killing
  the wrapper mid-call.
- Rules: "one invocation per task" → "invocations are sized, not counted".

### v4.0.2 — timeout hardening + model policy (facts verified on the reference machine)

**Harness ceiling raised** (install step, `~/.claude/settings.json` env block):
`BASH_DEFAULT_TIMEOUT_MS=600000`, `BASH_MAX_TIMEOUT_MS=1800000`. This removes the two
real killers: the 120 s default that murders any codex call whose runner forgot the
`timeout` parameter, and the 600 s stock ceiling that killed the measured 23-minute run.
Applies to subagent Bash calls too (verified against code.claude.com/docs/en/env-vars).

**Invocation hardening** (`agents/codex-implementer.md`):
- Inner cap derived, not hardcoded: `CAP = BASH_MAX_TIMEOUT_MS/1000 − 60` — stays
  observable under any ceiling, stock or raised.
- `timeout -k 10` TERM→KILL escalation. Verified empirically on the reference machine
  (Git Bash / MSYS coreutils 8.32): the kill propagates through the npm shim's
  `exec`'d node launcher to the native codex.exe — whole tree dies, no orphan keeps
  writing to the repo. Fallback documented: `ps -W` for the Windows PID, then
  `taskkill //PID <winpid> //T //F`.
- **Resume corrected against the real CLI** (codex-cli 0.146.1): `codex exec resume`
  rejects `--sandbox`/`--cd` (inherits both from the session) — the previous "same
  flags" instruction was wrong. Session id is captured from the first event of the
  `--json` stream (UUID in the `session_meta` event; same id as the
  `~/.codex/sessions/**/rollout-*-<uuid>.jsonl` filename), so `resume --last` is now
  only a last-resort fallback, not the happy path.
- `--json > "$LOG"`: event stream goes to a temp file, not the runner's context —
  session id + timeout forensics without paying tokens for the stream.
- `--cd "$(pwd -W 2>/dev/null || pwd)"`: Windows-native path under Git Bash.
- Report gains a `LANE:` line (model + effort from the run header) so the architect
  sees what actually ran.

**Model policy — config is SOT** (diverges from upstream's per-file model pins):
the lane passes **no** `--model` / `-c model_reasoning_effort` flags; `~/.codex/config.toml`
(maintained at the latest tier by the machine owner) governs. Upstream repins
(Sol→Luna→…) no longer need merging into flag lines, and stale slugs can't break the
lane when tiers rotate. A caller's spec may still pin a model/effort per piece.
Upstream's AGENTS.md-refusal patch (spec preamble + `STATUS: refused` + empty-diff
rule) is kept, with the preamble reworded for config-SOT.

Considered and rejected: running codex via Bash `run_in_background` (works in
subagents, but swaps a verified foreground cap for notification-timing mechanics and
loses the inner-timeout observation), and a PreToolUse `updatedInput` hook forcing the
`timeout` parameter (solved more simply by raising `BASH_DEFAULT_TIMEOUT_MS`, which
covers forgotten parameters everywhere, not just matched commands).

## Maintenance

- This clone was created shallow by the plugin installer; it has been `--unshallow`ed
  so upstream merges work. If you re-clone, run
  `git fetch --unshallow origin && git remote add upstream https://github.com/DannyMac180/fable-advisor.git`.
- Upstream release → `git fetch upstream && git merge upstream/main`, resolve
  (expect conflicts in plugin.json version and, if upstream touches them, the two
  patched files — upstream model repins resolve to "no flags, config is SOT"),
  bump patch version, push, `claude plugin update fable-advisor@fable-advisor-k`.
- Version scheme: upstream X.Y.0 → this fork ships X.Y.1 (and +1 per local fix).
