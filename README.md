# fable-advisor-k

> 이 저장소는 업스트림 `DannyMac180/fable-advisor`의 패치 fork입니다. 플러그인의 `name`은 `fable-advisor` 그대로이므로 호출명(`/fable-advisor:orchestration`, `fable-advisor:codex-implementer` 등)도 업스트림과 동일하게 유지됩니다.

## 이 fork가 다른 점

- `codex` 레인에 맡길 스펙을 하나의 위임당 하나의 산출물, 약 5분 분량으로 나누며 여러 산출물을 한 번에 묶지 않습니다.
- timeout을 레인 장애가 아니라 "작업이 너무 크다"는 크기 판정 신호로 취급합니다. timeout이 난 통스펙을 Fable 레인으로 재라우팅하는 업스트림 v4와 달리, 이 fork는 스펙을 분할한 뒤 `codex`로 재위임합니다.
- 큰 작업은 `codex exec resume <session-id>` 체인으로 짧은 호출들을 순차 연결하여 처리합니다.
- `codex-implementer`의 shell timeout을 540초로 설정하여 Claude Code Bash tool 자체의 600초 kill보다 먼저 timeout을 관측하고 보고합니다. Bash tool 호출에는 `timeout: 600000`을 명시해야 합니다.
- 2026-07 `structured-finance` 저장소에서 동일 작업을 측정한 결과, 통스펙은 23.3분 만에 timeout으로 kill되어 작업이 유실됐지만, 분해한 STOP-scoped 스펙은 8.1분 만에 완료됐습니다.

상세 내용은 [PATCHES-K.md](PATCHES-K.md)를 참고하십시오.

## 설치

```bash
claude plugin marketplace add Hanriverflow/fable-advisor-k
claude plugin install fable-advisor@fable-advisor-k
```

업스트림 원본(`fable-advisor@fable-advisor`)을 이미 설치해 사용 중이었다면 기존 마켓플레이스를 먼저 제거하십시오.

```bash
claude plugin uninstall fable-advisor@fable-advisor
claude plugin marketplace remove fable-advisor
```

## grok 레인

업스트림 v4는 `grok` 레인을 제거했습니다. 필요하면 upstream v3.1 트리의 [`grok-implementer.md`](https://github.com/DannyMac180/fable-advisor/blob/b3b50a9/agents/grok-implementer.md)를 `~/.claude/agents/`에 개인 에이전트로 두어 v4 라우팅과 공존시킬 수 있습니다.

## 업스트림 동기화

1. `git fetch upstream && git merge upstream/main`
2. 충돌을 해결합니다. 대상은 `.claude-plugin/plugin.json`의 버전과, 업스트림이 수정했다면 패치된 두 파일 `skills/orchestration/SKILL.md`, `agents/codex-implementer.md`입니다.
3. 버전을 bump합니다. 업스트림이 X.Y.0을 내면 이 fork는 X.Y.1로 올리고, 로컬 수정마다 1씩 더합니다.
4. push한 뒤 `claude plugin update fable-advisor@fable-advisor-k`를 실행합니다.

---

*이하는 업스트림 v4.0.0 README 원문.*

# Fable Advisor

**Opus runs the show. Cheaper typing, smarter escalation, and a Fable review before anything ships.**

Claude Code lets every subagent run on a different model — and lets the session itself run on a different model than its subagents. This plugin exploits that with the **architect pattern**: your session runs on **Opus**, acting as a full-time architect. It owns requirements, decomposition, specs, and verification — routes every implementation task to the right lane — and gets a **Fable 5** review of the finished work before calling anything done:

| Lane | Producer | Invocation | Route here when |
|---|---|---|---|
| Routine | **GPT-5.6 Sol** (high reasoning) | `codex-implementer` agent (default) | The spec fully determines the outcome — Codex does the typing via the [Codex CLI](https://github.com/openai/codex) |
| High-complexity | **Fable 5** | `fable-implementer` agent | One-off tasks where judgment the spec can't capture decides the outcome: subtle concurrency, hard debugging, security-sensitive paths, wide refactors |
| Review | **Fable 5** | `fable-advisor` agent | Commitment boundaries, and **always once at the end** — the advisor reviews the accumulated changes before the architect reports done |

Tokens route by capability: Opus emits judgment and specs, the cheap cross-vendor lane emits the bulk of the code, and Fable — the most expensive model available — is spent only where it changes outcomes: the hardest implementations and the final review. Because the routine lane is a *different model family* than the architect, cross-vendor review is built into the routing, not bolted on. For high-stakes work, run `codex-implementer` and `fable-implementer` on the same spec and let the architect pick the stronger diff.

The plugin ships the **orchestration skill** — the routing doctrine that teaches the session when to use each lane, the cost discipline that keeps expensive-model token volume minimal (emit judgment not volume, keep context lean, reason once then hand off), the five-part spec contract that makes context-free delegation safe, and the verification rules that keep every lane honest.

## Install

```
claude plugin marketplace add DannyMac180/fable-advisor
claude plugin install fable-advisor@fable-advisor
```

Updating an existing installation to the latest release:

```
claude plugin marketplace update fable-advisor
claude plugin update fable-advisor@fable-advisor
```

Then start your session as the architect:

```
/model opus
```

**Lite mode — one file, 30 seconds.** Don't want the full pattern? Copy [`agents/fable-advisor.md`](agents/fable-advisor.md) into `~/.claude/agents/` and keep your session on Sonnet. You get advisor consults at commitment boundaries without the orchestration layer (see "Advisor-only mode" below).

## Requirements

- **Claude Code ≥ 2.1.170** with a subscription that includes Fable 5 (Pro, Max, Team, or Enterprise — all current consumer plans qualify).
- **No Fable access** (e.g. API-key billing)? Change `model: fable` → `model: opus` in the advisor and implementer files. Same pattern, the Fable roles shift down to Opus.
- **Codex lane (the default implementer):** the `codex-implementer` agent needs the [OpenAI Codex CLI](https://github.com/openai/codex) installed and authenticated (`npm i -g @openai/codex`, then `codex login`). It invokes **GPT-5.6 Sol** as `gpt-5.6-sol` with `model_reasoning_effort=high`. GPT-5.6 access may be limited during preview; without model access, an installed/authenticated CLI, or successful authentication, the agent reports `STATUS: unavailable` — it never silently falls back to a Claude model — and the Fable lanes remain unaffected.
- Heads-up: if a pinned Claude model isn't available on your account, Claude Code silently falls back to your session model — the pattern degrades quietly rather than erroring. If results feel unremarkable, check your plan. (This quiet fallback applies only to Claude model pins — the codex lane always fails loudly with a structured error.)

Model resolution order in Claude Code: `CLAUDE_CODE_SUBAGENT_MODEL` env var → per-invocation `model` parameter → agent frontmatter → session model.

## Use it

With the session on Opus, just ask for work — the orchestration skill routes it:

```
Add rate limiting to our public API. Design it, delegate the
implementation, and verify the evidence before you call it done.
```

The architect writes the spec, picks the lane (rate limiting touches concurrency — a good case for `fable-implementer`, or for racing it against `codex-implementer` and picking the stronger diff), reads the diff and verification evidence when the report comes back, sends the finished work to `fable-advisor` for the final review, and only then reports done.

To make the doctrine always-on, add one line to your project's `CLAUDE.md`:

```
You are the architect — minimize your own token volume. Delegate all
implementation through the orchestration skill's routing table (never
type code yourself), delegate broad codebase exploration to cheap
read-only agents, verify evidence before accepting any lane's report,
and get a fable-advisor review before reporting any deliverable done.
```

## Commitment boundaries and the final review

Even the architect gets a second opinion. The `fable-advisor` agent is a read-only skeptic — consulted before architecture decisions, migrations, API designs, whenever a problem has resisted two attempts, and **always once at the end of a deliverable**, where it reads the accumulated diff with fresh eyes, against the stated goal rather than the conversation, and returns ship / fix-first / rethink. It never implements. It sees the code fresh, without your conversation's accumulated assumptions — that context-clean skepticism is what the final review buys.

## Advisor-only mode (the original pattern)

The minimal arrangement, for when you'd rather skip the orchestration layer: run the session on Sonnet and consult `fable-advisor` only at commitment boundaries.

```
Migrate our checkout sessions from Postgres to Redis — plan it,
consult your advisor before committing, then implement.
```

A typical consult costs cents. To make it automatic, add to your project's `CLAUDE.md`:

```
Before committing to any architecture decision, migration, or refactor
touching 3+ files, consult the fable-advisor agent and act on its verdict.
```

## FAQ

**Is this Anthropic's "advisor tool"?** No — that's a server-side API feature. These are plain Claude Code subagents plus a skill: readable, editable, no beta flags.

**Does this work on claude.ai?** No — subagent model routing is Claude Code only (CLI, desktop, VS Code, web).

**Why not just run everything on Fable?** You can. It's excellent. It's also the most expensive lane per token, and most of a session's tokens are orchestration and implementation mechanics that Opus and the codex lane handle at near-parity. Spend the premium where it changes outcomes: the hardest tasks and the final review.

**Upgrading from v3?** v4 restructures the routing: the session architect moves from Fable to **Opus**, the Grok 4.5 lane is **removed**, `codex-implementer` (GPT-5.6 Sol) becomes the default typing lane, and Fable's premium is refocused on the new `fable-implementer` high-complexity lane plus a now-mandatory end-of-deliverable `fable-advisor` review. If you still want the Grok lane, grab [`grok-implementer.md` from the v3.1 tree](https://github.com/DannyMac180/fable-advisor/blob/b3b50a9/agents/grok-implementer.md).

**Why a GPT lane in a Claude plugin?** Vendor diversity. Models from one family share blind spots; an independent implementation from a different lineage catches what same-family review misses — and with Claude as the architect and reviewer, every routine diff gets cross-vendor review for free. The architect and reviewer stay Claude — the routine lane is a producer, not a judge.

## Go deeper

I write [**Attention Heads**](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=fable-advisor) — deep, evidence-backed writing on AI, cognition, and agentic engineering. The **Agentic Engineering Field Notes** series is where I publish practical advice on the craft of using AI. [Subscribe](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=fable-advisor) to get new posts to your inbox.

## License

MIT
