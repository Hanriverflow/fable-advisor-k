# fable-advisor-k — delta from upstream

This repository is a hardened fork of [DannyMac180/fable-advisor](https://github.com/DannyMac180/fable-advisor). The plugin remains named `fable-advisor`, so skill and agent invocation names match upstream; only the marketplace and repository identity use `fable-advisor-k`.

The current release is based on upstream `4d6cc62` (2026-09-02, v5.0.0 plus README demo assets) and adds the K patches described below. The fork release is `5.0.1`.

## Upstream v5 integrated

- Fable 5.1 is the architect and clean-context final reviewer through the `fable` alias.
- GPT-5.6 Luna is the routine implementation lane.
- GPT-5.6 Sol replaces the old Fable implementation lane for judgment-heavy one-offs.
- Every implementation spec has six parts, adding `REASONING: <effort>`.
- Luna accepts efforts `low` through `max`; Sol additionally accepts `ultra`.
- The optional official Codex plugin can provide adversarial review, ordinary review, rescue, and setup flows.
- The upstream demo poster and video are included.

The upstream README changes after the v5 functional commit contained a split Subscribe URL and a duplicated dash. This fork repairs both while adapting the README to the fork's installation and runtime policy.

## Why the K patches exist

A foreground `codex exec` launched inside a Claude Code Bash tool call is bounded twice: by an inner shell timeout when available and by the tool call's own wall clock. If the outer tool kills first, the wrapper loses the opportunity to classify the result, preserve concise diagnostics, and report partial work.

Measurements on the reference Windows/Git Bash machine in 2026-07 showed the cost of oversized specs: a bundled structured-finance task was killed after 23.3 minutes, while STOP-scoped pieces completed in 8.1 minutes total. The K policy therefore treats timeout primarily as a task-sizing signal, not a reason to buy a more expensive model.

## K patch 1 — task sizing and cause-specific recovery

`skills/orchestration/SKILL.md` adds:

- One cohesive deliverable per Codex piece: approximately five minutes for Luna and ten minutes for Sol.
- Sequential resume chains for related pieces and parallel execution only for independent files in isolated write contexts.
- Write-early, verify, then STOP tails so useful disk state survives a kill.
- Cause-specific routing:
  - `timeout` → split and retry in the same lane;
  - `unavailable` → surface the access/install/auth error and transparently choose another adequate route;
  - `refused` → fix the conflicting policy or invalid request;
  - `partial` → verify what landed and delegate only the remainder.

Both implementation agents repeat the sizing rule locally because they receive no architect conversation context.

## K patch 2 — observable timeout and resumable execution

Both `agents/codex-implementer.md` and `agents/sol-implementer.md` use the same hardened execution pattern:

- Recommended Claude Code environment:

  ```json
  {
    "env": {
      "BASH_DEFAULT_TIMEOUT_MS": "600000",
      "BASH_MAX_TIMEOUT_MS": "1800000"
    }
  }
  ```

- The runner must set the Bash tool call's timeout parameter to the echoed `BASH_MAX_TIMEOUT_MS` value.
- The inner cap is derived as `BASH_MAX_TIMEOUT_MS / 1000 - 60`, leaving a one-minute observation window before the outer kill.
- `timeout -k 10` escalates TERM to KILL. On the reference machine, MSYS coreutils propagated the kill through the npm/node launcher to the native Codex process tree.
- Exit codes 124 and 137 are both recognized as timeout outcomes.
- `--json` is redirected to a unique temporary log instead of filling the wrapper's context.
- The session ID is parsed specifically from the `thread.started` event's `thread_id`, rather than taking the first UUID-like string in mixed stdout/stderr.
- Later pieces use `codex exec resume <session-id>`. Resume does not receive `--sandbox` or `--cd`; it inherits both from the original session. The lane model and piece effort are passed again because resume reloads global defaults for them.
- `resume --last` is a last-resort fallback only when no concurrent Codex run could be selected accidentally.
- `pwd -W` supplies a Windows-native working path under Git Bash, with plain `pwd` elsewhere.
- Reports state the lane model and effort actually passed on the command. An omitted effort is labeled `configured default` rather than guessed.

The resume chain was live-tested with Codex CLI 0.146.1 on 2026-08-08. On 2026-09-03, Codex CLI 0.152.1 help was rechecked: `exec` still supports `--model`, `--config`, `--sandbox`, `--cd`, `--json`, and `--output-last-message`; `exec resume` still accepts a session ID, `--config`, `--model`, `--json`, and `--output-last-message`, while exposing neither `--sandbox` nor `--cd`. A live Luna resume without `--model` reloaded the machine's global Sol default and emitted a model-switch warning, which is why both lane recipes repeat `--model` explicitly. A fresh Luna chain with the explicit model resumed without that warning and recalled its prior-turn token correctly.

## K patch 3 — lane model and effort policy

The v4 K fork used one machine-wide `~/.codex/config.toml` as the source of truth for both model and effort. That policy cannot represent two simultaneous v5 lane identities: with a global Sol pin, the routine and escalation agents would both run Sol.

Starting with v5.0.1:

- `codex-implementer` explicitly selects `gpt-5.6-luna`.
- `sol-implementer` explicitly selects `gpt-5.6-sol`.
- The architect selects effort per piece through the required `REASONING` spec line.
- A missing effort line falls back to the user's Codex configuration and is recorded in `GAPS`; it is not acceptable for an escalation.
- A lane never changes models on its own. A model change is an architect routing decision.

This deliberately retires the v4 single-config SOT. It preserves predictable lane semantics and lets routine work run at lower effort instead of inheriting an expensive global default.

## Refusal and evidence rules retained

The upstream 2026-08-04 refusal detection remains in both lanes:

- A scoped preamble opts the dedicated lane out of conflicting default orchestration rules while preserving all unrelated instructions.
- A clean process exit is not evidence of work.
- An empty requested diff is `STATUS: refused`, never `complete`.
- The wrapper reads the actual diff, re-runs verification, and compares Codex's final message with disk state.

## Maintenance

The clone has a named `upstream` remote:

```bash
git fetch upstream
git merge upstream/main
```

When resolving future upstream changes:

1. Keep the fork marketplace name, owner, homepage, and installation commands.
2. Preserve the upstream Fable/Luna/Sol architecture and effort table unless model capabilities change.
3. Preserve K sizing, derived timeout, JSON logging, session-ID parsing, resume, and cause-specific recovery in both Codex lanes.
4. Update this file's upstream commit and CLI verification note.
5. Run `claude plugin validate .`, JSON parsing, stale-reference searches, and a live low-effort smoke test before release.

Versioning: an upstream `X.Y.0` becomes the first K release `X.Y.1`; subsequent K-only fixes increment the patch number.
