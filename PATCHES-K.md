# fable-advisor-k — delta vs upstream

Fork of [DannyMac180/fable-advisor](https://github.com/DannyMac180/fable-advisor), carrying
task-sizing patches for the codex lane. Plugin name stays `fable-advisor` so all
skill/agent invocations (`/fable-advisor:orchestration`, `fable-advisor:codex-implementer`, …)
are identical to upstream; only the marketplace/repo identity is `-k`.

## Why (measured, 2026-07 / structured-finance repo)

A single `codex exec` under Claude Code's Bash tool dies at the 10-minute call cap
(default is 2 minutes). GPT-5.6 Sol at high reasoning rabbit-holes on bundled specs:
the same task took 23.3 min (timeout kill, work lost) as one monolith vs 8.1 min when
decomposed with a STOP-scoped spec. Upstream v4 re-routes a timed-out monolith to the
Fable lane — the most expensive model — instead of splitting it.

## The patches

`skills/orchestration/SKILL.md` (architect side):
- New **"Task sizing — keep codex calls short"** section: one deliverable per delegation
  (~5-minute pieces), chain instead of bundling, write-early-then-STOP spec tails.
- Re-route rule split: `unavailable` → fable-implementer with the same spec (upstream
  behavior); `timeout` → **split first**, re-delegate to codex, escalate only for
  judgment failures, not size.
- Description gains the sizing/timeout triggers.

`agents/codex-implementer.md` (lane side):
- New **"Size the work — sequence anything big"** section: sequential short `codex exec`
  calls, context carried between pieces via `codex exec resume <session-id>`
  (`--last` only when no concurrent codex run is possible).
- Shell timeout 600 s → **540 s** so it fires before the Bash tool's own 600 s kill:
  timeouts get observed and reported (`STATUS: timeout` + partial work on disk)
  instead of killing the wrapper mid-call. Bash tool call itself must set
  `timeout: 600000` (the 120 s default kills codex mid-run).
- Spec tail: write files to disk early, verify, then STOP — no exploration.
- Rules: "one invocation per task" → "invocations are sized, not counted"
  (sequencing allowed; scope never exceeds the caller's spec).

## Maintenance

- Upstream release → `git fetch upstream && git merge upstream/main`, resolve
  (expect conflicts in plugin.json version and, if upstream touches them, the two
  patched files), bump patch version, push, `claude plugin update fable-advisor@fable-advisor-k`.
- Version scheme: upstream X.Y.0 → this fork ships X.Y.1 (and +1 per local fix).
