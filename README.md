# fable-advisor-k

> [DannyMac180/fable-advisor](https://github.com/DannyMac180/fable-advisor)의 hardened fork입니다. 플러그인 이름은 `fable-advisor` 그대로이므로 `/fable-advisor:orchestration`, `fable-advisor:codex-implementer` 같은 호출명은 업스트림과 같습니다. 마켓플레이스와 저장소 이름만 `fable-advisor-k`입니다.

**Fable 5.1이 설계하고, Luna와 Sol이 작업별 effort로 구현하며, Fable 5.1이 출고 전 검토합니다. K fork는 이 흐름에 작업 분할, 관측 가능한 timeout, 안전한 resume 체인을 추가합니다.**

<a href="https://github.com/Hanriverflow/fable-advisor-k/raw/main/assets/fable-advisor-demo.mp4"><img src="assets/fable-advisor-demo-poster.png" alt="30-second demo: Fable 5.1 orchestrates, GPT-6 Luna implements, Fable 5.1 reviews" width="100%"></a>

<p align="center"><em>▶ 30초 데모 — Fable 5.1 설계 → GPT-6 Luna 구현 → Fable 5.1 검토</em></p>

## 구조

| Lane | Producer | 호출 | 사용 시점 |
|---|---|---|---|
| Routine | **GPT-6 Luna** | `codex-implementer` | 스펙이 결과를 충분히 결정하는 일반 구현, wiring, CRUD, 기계적 수정, 표준 테스트 |
| High-complexity | **GPT-6 Sol** | `sol-implementer` | 동시성, 보안, 비정형 알고리즘, 어려운 디버깅, 넓은 refactor, 또는 Luna의 교정된 시도 두 번이 실패한 작업 |
| Review | **Fable 5.1** | `fable-advisor` | 주요 설계 결정을 내리기 전과 모든 deliverable의 최종 검토 |

모델은 lane이 결정하고, architect는 스펙의 여섯 번째 항목인 `REASONING: <effort>`로 작업별 effort를 결정합니다. Luna는 `low`부터 `max`, Sol은 `low`부터 `ultra`까지 지원합니다. 지원하지 않는 effort는 접근 실패가 아니라 잘못된 spec이므로 `STATUS: refused`로 반환하며 다른 lane으로 자동 전환하지 않습니다. 전역 `~/.codex/config.toml`은 누락된 값의 fallback일 뿐 lane 정체성의 source of truth가 아닙니다.

## K fork가 추가하는 것

- **논리적 경계 우선:** 한 번의 위임에는 독립적으로 검증 가능한 응집된 산출물 하나를 담습니다. 시간만 보고 함수 구현 중간, schema와 consumer 사이, migration과 호환 코드 사이를 자르지 않습니다. 타입·인터페이스, 모듈과 직접 테스트, migration 단계처럼 검증 가능한 경계에서만 나눕니다.
- **10분은 checkpoint 목표:** Luna는 약 5분, Sol은 약 10분 안에 첫 번째 유용한 상태를 디스크에 기록하는 것을 목표로 합니다. 이는 강제 종료 시간이 아닙니다. 아래 권장 30분 ceiling에서는 논리적 완결성을 지키기 위해 Sol 조각이 10분을 넘어 계속될 수 있으며, 기본 600초 ceiling에서는 540초 내부 cap보다 충분히 짧게 분할합니다.
- **원인별 복구:** `timeout`은 모델 실패가 아니라 작업 크기 신호로 취급해 같은 lane에서 먼저 분할합니다. `unavailable`, `refused`, `partial`은 각각 다른 원인으로 처리합니다.
- **권한 차단:** Claude Code의 permission system 또는 auto-mode가 Codex 실행이나 spec 작성 등 선행 작업을 막으면 `blocked`로 즉시 중단합니다. 관측한 메시지와 차단 단계를 보고하고 사용자의 명시적 결정을 기다립니다. 프롬프트·플래그·실행 경로나 다른 lane으로 우회하지 않으며, Codex 자체 인증·접근 오류인 `unavailable`과 구분합니다.
- **resume 체인:** 관련 조각은 `codex exec resume <session-id>`로 순차 연결합니다. `thread.started` JSON 이벤트의 `thread_id`를 사용하고 lane 모델을 다시 명시합니다. 최초 실행과 매 resume 직전에 현재 조각의 effort를 검증하고 `EFFORT_ARGS`를 비운 뒤 새로 구성합니다. 생략이 허용되는 단순 작업에서는 이전 override를 제거하고 전역 설정으로 fallback하며, 고난도 작업에는 명시적 effort가 필요합니다. 새 Bash 호출에서는 SID와 이전 artifact 경로를 복원합니다. `resume --last`는 동시 세션이 없을 때만 최후 수단으로 사용합니다.
- **관측 가능한 timeout:** 내부 cap을 `BASH_MAX_TIMEOUT_MS / 1000 - 60`으로 계산하고 `timeout -k 10`으로 TERM→KILL을 수행합니다. 외부 Bash tool이 먼저 종료하지 않도록 해당 tool call의 timeout도 같은 상한으로 설정합니다.
- **진단 가능한 실행:** Codex의 JSON 이벤트와 마지막 메시지를 임시 파일에 기록하고, rc 124와 137을 timeout으로 식별합니다. 검증된 `complete` 결과는 모든 조각의 임시 파일을 삭제합니다. 그 밖의 실행 결과는 spec을 삭제하고 모든 조각의 final-message와 JSON log만 보존해 `ARTIFACTS`에 절대 경로를 보고합니다. 단, `blocked`이면 추가 검증·정리 호출 없이 앞선 변경과 spec을 포함한 기존 artifact를 보존·보고합니다. artifact가 생성되지 않았다면 `ARTIFACTS: none`이며, 실행되지 않은 Codex의 종료코드나 로그를 추정하지 않습니다. 보고서에는 실제 명령에 전달한 lane 모델과 effort를 적고, effort를 생략했다면 추측하지 않고 `configured default`로 표시합니다.
- **Windows/Git Bash 대응:** 최초 실행의 working directory는 `pwd -W`가 있으면 Windows-native 경로를 사용합니다. Resume에는 CLI가 받지 않는 `--sandbox`와 `--cd`를 전달하지 않되, 전역 기본값으로 바뀔 수 있는 모델과 effort는 다시 전달합니다.
- **무음 거부 감지:** `exit 0`이어도 요청한 diff가 비어 있으면 성공이 아니라 `STATUS: refused`로 처리합니다.

상세한 업스트림 대비 변경 이력은 [PATCHES-K.md](PATCHES-K.md)에 있습니다.

## 설치

```bash
claude plugin marketplace add Hanriverflow/fable-advisor-k
claude plugin install fable-advisor@fable-advisor-k
```

Claude Code의 `~/.claude/settings.json`에서 Bash tool의 기본 및 최대 실행시간을 올리는 것을 권장합니다.

```json
{
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "600000",
    "BASH_MAX_TIMEOUT_MS": "1800000"
  }
}
```

이 설정에서 내부 cap은 1,740초(29분)입니다. 설정을 적용하지 않으면 기본 600초 ceiling에서 내부 cap이 540초(9분)이므로 Sol 조각도 9분보다 충분히 짧아야 합니다. 권장 설정에서는 응집된 조각이 15~20분 걸려도 10분마다 기계적으로 자르지 않고, 약 10분 안에 첫 durable checkpoint를 기록한 뒤 논리적 완료 지점까지 이어갑니다. 환경 변수만으로 Bash tool call의 실제 timeout이 바뀌지는 않으므로, 각 호출의 timeout parameter도 `BASH_MAX_TIMEOUT_MS`와 같은 값으로 설정해야 합니다.

그다음 architect 세션을 시작합니다.

```text
/model fable
```

이미 업스트림 marketplace를 설치했다면 이름 충돌을 피하기 위해 먼저 제거합니다.

```bash
claude plugin uninstall fable-advisor@fable-advisor
claude plugin marketplace remove fable-advisor
```

## 업데이트

```bash
claude plugin marketplace update fable-advisor-k
claude plugin update fable-advisor@fable-advisor-k
```

업데이트 후에는 Claude Code를 재시작해야 새 agent와 skill이 로드됩니다.

## 요구사항

- **Claude Code 2.1.170 이상**과 Fable 5.1을 사용할 수 있는 구독. Agent는 `model: fable` alias를 사용합니다.
- **OpenAI Codex CLI** 설치 및 로그인. 두 구현 lane 모두 `codex exec`를 사용합니다.

```bash
npm i -g @openai/codex
codex login
```

Luna나 Sol에 접근할 수 없거나 CLI 인증이 실패하면 lane은 `STATUS: unavailable`과 실제 오류를 반환하며 다른 모델로 조용히 대체하지 않습니다. Fable을 사용할 수 없는 API-key 환경이라면 `agents/fable-advisor.md`의 `model: fable`을 `model: opus`로 바꾸고 세션도 Opus에서 실행할 수 있습니다.

## 사용

일반 요청을 하면 orchestration skill이 lane과 effort를 선택하고, 결과 diff와 verification evidence를 검토한 뒤 `fable-advisor`의 최종 verdict를 받습니다.

```text
공개 API에 rate limiting을 추가해. 설계하고, 적절한 lane과 effort로
구현을 위임하고, 검증 evidence와 최종 review까지 확인한 뒤 완료해.
```

프로젝트의 `CLAUDE.md`에 다음 규칙을 두면 이 패턴을 항상 적용할 수 있습니다.

```text
You are the architect. Use the orchestration skill to delegate implementation,
name a reasoning effort for every task, keep Codex calls small and resumable,
verify the actual diff and commands, and obtain a fable-advisor review before
reporting any deliverable complete.
```

## 선택 사항: 공식 Codex plugin

[OpenAI Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc)은 필수 의존성이 아니지만 독립 모델 review와 진단 흐름을 추가할 수 있습니다.

```text
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

- 보안, migration, API 변경에는 Fable 검토 전에 `/codex:adversarial-review`를 사용할 수 있습니다.
- 일반 변경에는 `/codex:review`, 설치와 로그인 문제에는 `/codex:setup`을 사용할 수 있습니다.
- `/codex:rescue`는 사용자가 background workflow를 원할 때만 사용합니다. Architect는 여전히 diff를 읽고 verification을 다시 실행해야 합니다.
- stop-time review gate는 필수 Fable review와 중복되어 loop가 생길 수 있으므로 기본적으로 켜지 않습니다.

## Advisor-only와 fallback

전체 orchestration이 필요 없다면 `agents/fable-advisor.md`만 개인 agent 디렉터리에 복사해 advisor-only 방식으로 사용할 수 있습니다. v5에서는 기본 high-complexity lane이 Sol이며, 예전 Claude 구현 lane은 제거되었습니다. Codex를 사용할 수 없을 때 Claude 구현 agent가 꼭 필요하면 [업스트림 v4의 `fable-implementer.md`](https://github.com/DannyMac180/fable-advisor/blob/ad2bdc3/agents/fable-implementer.md)를 별도 fallback agent로 설치하십시오. 자동 fallback으로 연결하지는 마십시오.

## 업스트림 동기화

```bash
git fetch upstream
git merge upstream/main
```

충돌 해결 시 다음 원칙을 유지합니다.

1. marketplace 이름, owner, homepage는 K fork 값을 유지합니다.
2. 모델은 Luna/Sol lane이, effort는 six-part spec이 결정합니다.
3. 두 Codex lane 모두 K fork의 sizing, derived timeout, JSON log, session ID, resume 규칙을 유지합니다.
4. `timeout`은 먼저 분할하고, `unavailable`과 `refused`는 원인에 맞게 처리합니다.
5. `PATCHES-K.md`의 기준 커밋과 검증한 CLI 버전을 갱신합니다.

## 유지보수 검증

플러그인 runtime에는 Python이 필요하지 않습니다. 저장소를 수정하거나 업스트림을 병합할 때만 `uv` 기반 validator와 테스트를 실행합니다.

```bash
uv run tools/validate_repo.py .
uv run --with pytest python -m pytest -q tests
claude plugin validate .
```

validator는 JSON과 front matter, 선언 버전, lane 모델과 effort 집합, `blocked`를 포함한 여섯 report 상태, timeout/resume 토큰, 활성 agent 이름, 임시파일 수명 계약을 검사합니다. `tests/test_lane_commands.py`는 Markdown의 실제 Bash 예시를 추출하고 임시 PATH의 mock Codex로 effort 전환·생략·거부, 새 셸 resume, 기존 artifact 정책과 `bash -n` 문법을 검사합니다. Bash가 없으면 해당 검사는 skip으로 보고하며 통과로 세지 않습니다. 이 검증은 실제 Claude Code 권한 시스템이나 모델 호출의 end-to-end 검증이 아닙니다. README 설명문 자체는 고정하지 않으므로 문구를 자유롭게 개선할 수 있습니다. 인증과 비용이 필요한 live Codex smoke test는 일반 검증과 분리해 릴리스 전에 한 번 실행합니다.

## 배경과 저자

원 프로젝트와 architect pattern은 Dan McAteer가 만들었습니다. 저자의 [Attention Heads](https://attentionheads.substack.com/?utm_source=github&utm_medium=readme&utm_campaign=fable-advisor)에는 agentic engineering 관련 글이 있습니다. [구독 링크](https://attentionheads.substack.com/subscribe?utm_source=github&utm_medium=readme&utm_campaign=fable-advisor)도 참고할 수 있습니다.

## 라이선스

MIT
