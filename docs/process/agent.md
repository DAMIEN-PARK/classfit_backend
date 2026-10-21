---
type: Agent Guide
title: "Agent Guide: ClassFit 에이전트 편성표"
description: ClassFit 개발에서 움직이는 승인자·Claude 세션(리드·워커·reviewer·verifier)·CI 의 편성, 도구·권한, 작업 트리와 레인, 귀속, 에이전트가 하지 않는 것
date: 2026-10-21
tags: [agent-guide, classfit, agents, process, claude-code]
Archives: false
URL: ""
---

# ClassFit 에이전트 편성표

승인자는 `DAMIEN-PARK` 1인이다(r3 §1.1 ① 답). 에이전트는 계획을 쓰고 구현하고 검증하지만, 승인과 master 변경은 하지 않는다(r3 §3 원칙 ①, SDLC §6.4).

## 1. 편성표

| 이름 | 실행 위치 | 도구 | 권한 | 호출 시점 |
|---|---|---|---|---|
| 승인자 | 사람(DAMIEN-PARK). 병합은 Claude 밖 터미널 | git · `scripts/merge_task.sh` | 계획 승인(approve 빈 커밋) · 병합 · master push · 의존성 승인 | 계획 커밋 뒤 · 리뷰 Important 0 뒤 |
| 리드 세션 | 승인자의 Claude Code 세션(이 저장소) | 전부(훅·permissions.deny 적용) | 가지에 커밋. master 변경 없음 | 계획 작성 · 팀 편성 · 통합 |
| 팀 워커 | 리드가 띄운 Claude 세션(같은 작업 트리) | 전부(훅·deny 적용) | 계획 "바뀌는 파일"에 적힌 자기 소유 파일만 고친다. 파일을 지정해 커밋한다 | 계획 승인 후 구현 |
| verifier | 서브에이전트 `.claude/agents/verifier.md` | Bash, Read | 읽기·실행만. 파일 수정 없음 | 빌더가 "done"을 말하기 전. 계획 "증명" 절과 대조 |
| reviewer | 서브에이전트 `.claude/agents/reviewer.md`, **작성 세션과 다른 새 세션** | Read, Grep, Glob, Bash(git diff·log·show) | 읽기만. 소견은 호출한 세션이 계획 "리뷰" 절에 붙인다 | 병합 전. REVIEW.md 3패스, Important 0 까지 |
| CI | GitHub Actions `.github/workflows/ci.yml` | 결정론 스크립트만 | LLM 호출 없음, 키 없음 | master push · PR. gates 잡 · test 잡 |

## 2. 작업 트리·레인 배정

- **지금은 작업 트리 하나다.** worktree 를 쓰지 않는다. 승인자가 병합하는 동안 에이전트 세션은 멈춘다(r3 §5.1).
- 레인은 A 하나다([plan.md](plan.md) 2절).
- 한 태스크에 팀 워커를 여럿 두면, 그 계획의 "바뀌는 파일" 머리에 워커별 소유 파일을 적는다. 다른 워커의 파일은 고치지 않고, 같은 파일을 두 워커가 동시에 고치지 않는다(T0b 계획 전례).
- 같은 작업 트리에서 여러 세션이 커밋하므로 커밋은 `git commit -F <메시지 파일> -- <경로…>` 로 자기 파일만 담는다. 새 파일은 먼저 `git add <경로>` 한다.

## 3. 귀속

- 모든 세션·서브에이전트·CI 잡은 DAMIEN-PARK 에게 귀속된다.
- 에이전트 커밋은 트레일러 `Co-Authored-By: Claude …` 를 단다.
- 훅의 차단·허용은 stderr 메시지로 세션 기록에 남는다.

## 4. 에이전트가 하지 않는 것

1. **승인** — 계획·intent·spec 승인, 검토 완료 판정, 병합. 커밋 제목 `approve:` 와 트레일러 `Approved-by:` 는 승인자만 쓴다. 훅 `.claude/hooks/deny-approval.sh` 는 명령 문자열만 보므로, 메시지 파일(`-F`)이나 메시지 재사용으로 피해 가는 것도 같은 위반이다.
2. **master 변경** — master 에 직접 커밋·병합·push·reset 하지 않는다. update-ref·브랜치 강제 이동·`git fetch .`·rebase·cherry-pick 도 같다. 가지 갱신은 `bash scripts/sync_task.sh` 만 쓴다. 병합은 승인자의 `scripts/merge_task.sh` 다(r3 부록 E11).
3. **훅 우회** — `--no-verify`·`git commit -n`·훅 경로(`core.hooksPath`)나 `merge.ff` 설정 변경을 하지 않는다.
4. **뭉뚱그린 스테이징** — `git add -A`·`git add --all`·`git add .`·`git commit -a`/`--all` 을 쓰지 않는다. 파일을 지정해 커밋한다.
5. **사용자 미커밋 변경 건드리기** — 사용자가 고치고 커밋하지 않은 파일(예: alembic.ini)을 고치거나 커밋하지 않는다. checkout·restore·stash 로 되돌리는 것도 포함한다.
6. **테스트 약화** — 실패하는 시험을 삭제·skip 하거나 기대값을 바꿔 통과시키지 않는다. 시험 DB 가 없으면 skip 이 아니라 실패다(tests/conftest.py). 버그 픽스 모드에서는 훅이 tests 편집을 막는다.
7. **정책 완화** — CLAUDE.md·REVIEW.md·훅·`.claude/settings.json` 의 deny·gate·check 스크립트를 스스로 고쳐 통과시키지 않는다. 고칠 일이 보이면 묶어서 승인자에게 묻는다.
8. **운영 배포** — 배포 명령은 `RELEASE_APPROVAL=<이름>` 없이 돌지 않는다(`.claude/hooks/deploy-gate.sh`). 지금은 배포 명령이 없다.




---

# Resources

- SDLC 안내서 `2026-10-06-ai-native-sdlc-porting-guide.md` §6.4 agent 틀(저장소 루트)
- 승인된 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §1.1 · §3 · §5.1 · 부록 E11 · 승인 기록. 저장소 루트 기준 경로이고, `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 모양 참고: BHQ 편성표 `/Users/damienpark/Desktop/BHQ/plan/agent.md`(저장소 밖, 읽기만)
