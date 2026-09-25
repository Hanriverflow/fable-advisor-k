---
name: orchestration
description: Routing doctrine for a Fable 5.1 architect that delegates routine implementation to GPT-6 Luna, escalates judgment-heavy one-offs to GPT-6 Sol, selects reasoning effort per task, sizes Codex work under observable timeout limits, resumes related pieces safely, and obtains a Fable review before reporting done. USE WHEN delegating implementation, choosing a lane or effort, writing a subagent spec, recovering from timeout or refusal, deciding whether to consult fable-advisor, using optional Codex plugin review skills, managing model cost, or running a multi-task build where the session is the architect.
---

# Orchestration — the architect's routing doctrine

The session is the architect. It owns requirements, architecture, decomposition, interfaces, specs, routing, and acceptance. It should almost never type implementation code. Route each implementation task to the cheapest adequate lane at the lowest adequate reasoning effort, keep every CLI call small enough to finish observably, and obtain a clean-context Fable review before reporting a deliverable complete.

## Cost discipline — the prime directive

Fable 5.1 orchestrates and reviews. GPT-6 Luna performs routine typing. GPT-6 Sol takes the hard one-offs. Both implementation lanes are cross-vendor producers; Fable remains responsible for judgment and acceptance.

**Emit judgment, not volume.** The architect produces decomposition, interfaces, specs, routing decisions, and verdicts. Long implementation blocks, test bodies, boilerplate, and mechanical config belong in a lane. If a lane produces a bad diff, send a corrected spec instead of silently repairing it.

**Keep the context lean.** Delegate broad searches and log inspection to a cheaper read-only agent when available. Keep conclusions in the architect's context, not full files, JSON event streams, or verbose command output.

**Reason once, then hand off.** Make architectural and debugging decisions before delegation, capture them in the spec, and avoid paying to rediscover them across turns.

The architect always retains decomposition, interface design, debugging hypothesis selection, lane and effort routing, and judgment of verification evidence.

## The lanes

| Lane | Producer | Invoke | Route here when |
|---|---|---|---|
| Routine | GPT-6 Luna | `codex-implementer` | The spec determines the outcome: mechanical edits, wiring, CRUD, standard tests, and ordinary features. Default lane. |
| High-complexity | GPT-6 Sol | `sol-implementer` | Correctness depends on judgment the spec cannot fully encode: concurrency, security-sensitive paths, non-trivial algorithms, hard debugging, wide refactors, or two failed corrected attempts in the routine lane. |
| Review | Fable 5.1 | `fable-advisor` | Read-only advice at commitment boundaries and the mandatory end-of-deliverable review. |

The deciding question is how much the result depends on judgment the spec cannot capture. Little means Luna. A lot, with costly mistakes, means Sol. Give one corrected routine spec after the first miss; escalate only after the second miss shows the task was misclassified.

Model generation policy: the lanes run the GPT-6 family (`gpt-6-luna`, `gpt-6-sol`). Do not route back to GPT-5.6 models. `gpt-6-astra` (efforts up to `ultra`) is available for the hardest one-offs or a cross-vendor adversarial review through the optional Codex plugin (`--model gpt-6-astra`).

The lane determines the model. The architect determines reasoning effort per task. The user's global Codex config remains the fallback for omitted values, not the source of lane identity.

Handle abnormal outcomes by cause:

- `blocked`: if Claude Code's permission system or auto-mode denies a tool action (including Codex execution or creating/writing the task spec), stop immediately. Return `STATUS: blocked`, quote the observed denial and identify the blocked step in `GAPS`, inform the user, and obtain an explicit decision about permissions or how to proceed before any retry. Do not retry by changing the prompt, preamble, flags, script, or execution path, or send the same blocked action to another lane.
- `unavailable`: report the exact access, installation, or authentication error. Re-route only when the other lane is adequate, or transparently keep the work with the architect. Never silently substitute a model.
- `timeout`: treat it as a sizing verdict. Split the piece and resume the same lane before considering a different capability tier. Sol is not a remedy for a bundled spec.
- `refused`: read the quoted reason and fix the conflicting instruction or invalid request. Neither re-routing nor splitting cures a policy refusal.
- `partial`: inspect what landed, verify it, and write a spec only for the coherent remainder.

Distinguish a host tool denial from Codex authentication or account-access failures; keywords such as `permission` or `403` alone do not determine the status. A host block takes precedence as `blocked` even if earlier pieces produced verified changes. Preserve and report those changes and every existing temporary artifact, including specs, using the absolute paths already recorded. If no artifacts were created, report `ARTIFACTS: none`. Do not issue further tool calls for verification or cleanup while blocked; if cleanup is denied, report the retained paths and the cleanup limitation. If Codex did not start, report `not started` / `not run`; never invent a process exit code, log, final message, or verification evidence. The user's decision is required before continuing the blocked workflow.

Any other nonzero exit is classified from the observed cause and verified disk state, never from the exit code alone: access or authentication failures are `unavailable`, while verified incomplete changes or failed verification are `partial`. An unknown nonzero with no verified requested change is `unavailable`; keep the actual exit code and useful log tail in `GAPS`, label the cause unclassified, and diagnose it before re-routing. An outer-tool kill without an inner timeout result is `timeout` when no verified change landed or `partial` when one did; report the outer-kill evidence without inventing exit 124 or 137.

## Choosing reasoning effort

Pick the lowest rung adequate for the task. Effort changes cost and wall-clock behavior; it is not a dial to leave at maximum.

| Rung | Luna | Sol | Typical use |
|---|---|---|---|
| `low` / `medium` | yes | yes | Renames, boilerplate, wiring, configuration, and tests that mirror an existing pattern |
| `high` | yes | yes | Ordinary features with a few local design decisions |
| `xhigh` | yes | yes | Tricky logic, interacting multi-file changes, or a second corrected attempt |
| `max` | yes | yes | Concurrency, security-sensitive paths, and difficult debugging |
| `ultra` | no | yes | Sol-only internal delegation for wide refactors or problems that resisted two attempts |

If the requested rung is unsupported, the lane returns `STATUS: refused`, records the invalid value and supported set in `GAPS`, and asks for a corrected spec instead of rounding or re-routing. Use `unavailable` for installation, authentication, access, or model-availability failures and for an unclassified nonzero execution failure with no verified requested change; the unclassified case requires diagnosis before re-routing. A missing `REASONING` line falls back to the user's Codex default and is reported in `GAPS`; that is acceptable only for trivial work, never for an escalation.

The architect and advisor inherit Claude Code's session effort because their agent definitions pin none. Raise `/effort` before consequential architecture decisions or final reviews, then lower it for routine turns.

## The six-part spec contract

Implementers receive none of the architect's conversation context. Every delegation contains:

1. **Objective** — the coherent outcome, in one paragraph
2. **Files** — exact paths to create or modify
3. **Interfaces** — signatures, types, schemas, or API shapes to preserve
4. **Constraints** — conventions, boundaries, and things not to touch
5. **Verification** — commands that prove the result
6. **Reasoning** — exactly one line, `REASONING: <effort>`

A spec that cannot state all six parts is an undecided architecture problem, not implementation work.

## Task sizing — keep Codex calls short

Both implementation lanes drive one foreground `codex exec` at a time under a hard wall clock. The lane's inner timeout is derived as `BASH_MAX_TIMEOUT_MS / 1000 - 60`, so it fires before the Bash tool's outer kill and leaves a JSON log, session ID, final-message file, and partial disk state for diagnosis. Raising the ceiling creates headroom; it does not make bundling free.

- **Choose coherence before the clock.** A piece ends at an independently verifiable boundary: an interface, one module plus its direct tests, one migration phase, or another state that can build and pass its named check. Never split mid-function, between a schema and its consumer, or only because a target minute elapsed.
- **Treat five and ten minutes as checkpoint targets.** Luna should write useful state within about five minutes; Sol should do so within about ten minutes. These targets bound time to a durable checkpoint, not total piece duration.
- **Respect the actual cap.** Sol's ten-minute checkpoint target assumes the recommended 1,800-second ceiling. Under that 1,740-second inner cap, a cohesive 15–20 minute piece may continue to its logical boundary. Under the stock 600-second ceiling, keep every Sol piece comfortably below the 540-second inner cap.
- **Chain instead of bundle.** Related pieces run sequentially through `codex exec resume <session-id>`; independent pieces with no shared files may run in parallel.
- **Write early, verify, then stop.** Every piece writes useful state before extended exploration, runs its named verification, and stops without expanding scope.
- **Split a timeout.** Retry smaller halves in the same session. Do not resend the same oversized spec or switch models merely to buy more wall-clock time.
- **Keep resume exact.** Capture `thread_id` from the JSON `thread.started` event. Resume inherits sandbox and working directory, so do not pass `--sandbox` or `--cd`; repeat the lane's model because the CLI otherwise reloads global defaults. Before every invocation, including resume, validate the current piece's `REASONING` for its lane, reset `EFFORT_ARGS=()`, and build only that piece's effort override. Permitted omission clears the previous override and uses the configured default, with the omission in `GAPS`; escalation still requires explicit effort. New Bash tool calls must restore `SID` and prior absolute artifact paths and rebuild timeout and effort arguments. Use `--last` only when no concurrent Codex session can be mistaken for the target.

The recommended Claude Code environment is `BASH_DEFAULT_TIMEOUT_MS=600000` and `BASH_MAX_TIMEOUT_MS=1800000`. The runner must also set each Bash tool call's `timeout` parameter to the echoed ceiling; otherwise the tool can terminate before the inner timeout becomes observable.

## Parallelism

Launch independent specs in parallel only when they share neither files nor ordering dependencies. Keep sequential chains and single-file surgery serial. For high-stakes work, Luna and Sol may independently attempt the same spec in isolated worktrees; never race two write-capable lanes in one working tree.

## Commitment boundaries and final review

Consult `fable-advisor` before architecture choices, migrations, public API shapes, security-sensitive designs, wide refactors, and after two genuinely different failed attempts.

Always consult it once more at the end of a deliverable. Pass the stated goal, accumulated diff, verification evidence, and any unresolved concern. The architect must act on the verdict or explicitly surface a disagreement before reporting done.

The advisor and architect are the same model in separate contexts, so this is a fresh-eyes check rather than an independent-family review. Cross-vendor independence comes from the Codex lanes and, when installed, the optional Codex plugin.

## Optional Codex plugin

If `codex@openai-codex` is enabled in Claude Code:

- Use `/codex:adversarial-review` before the Fable review for security-sensitive paths, migrations, and API changes. `/codex:review` is the lighter ordinary pass.
- Use `/codex:rescue --model <slug> --effort <rung>` only when the user asks for that workflow or wants a background investigation. The architect still reads the diff and re-runs verification. Prefer the lanes when structured reports, empty-diff detection, or `max`/`ultra` effort is required.
- Use `/codex:setup` to diagnose installation, version, or login failures.

Leave the plugin's stop-time review gate disabled by default because it overlaps the mandatory advisor review and can loop. The plugin is optional; the lanes invoke the local Codex CLI directly.

## Verification

Reports are claims, not evidence. Before accepting lane work, read the actual diff, compare it with the objective and constraints, and re-run the verification command. A clean exit with no requested diff is a refusal, not success. A spec gap receives a corrected spec, not an instruction to guess.
