---
type: Task Plan
title: "Plan: T10 phase1-close"
description: T9b 병합·push 뒤 1차 마감 기록만 남기는 문서 전용 태스크 계획 — spec 1절 plan.md 행 "1차 완료" · check_docs ④ 대상 행 수 · E-15(T9b 병합 커밋 CI) 결론을 T9b 계획 기록 칸과 plan.md 에 적는다. 코드·마이그레이션 없음
date: 2026-10-24
tags: [plan, task, t10, phase1-close, docs, classfit]
Archives: false
URL: ""
---

# Plan: T10 phase1-close (from plan.md#T10, 2026-10-24)

- 근거: T9b 계획 [`docs/plans/T9b-inquiry-home.md`](T9b-inquiry-home.md) 결정 xxvi(1차 마감 — 문서 전용 가지) · 작업 순서 10·11 · 기록 칸 "병합 뒤 `check_docs.sh` ④ 대상 행 수 · E-15 결론" · 태스크 [`docs/process/plan.md`](../process/plan.md) 2절 단계 표 "마감 | T10" · 3절 T10 행 · 1차 끝 문단(:64) · r3 §6 E-15 · 192("개수 기준은 1차 마지막 병합(T9b) 기준"). master 에 직접 커밋할 수 없어(CLAUDE.md) 병합 뒤 기록을 이 가지가 쓴다.
- 승인:
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T10" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 문서 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.
- 가지: `T10-phase1-close` 를 master 의 `1643ebc merge: T9b inquiry-home` 에서 땄다(T9b 결정 xxvi — `P1-close` 는 `scripts/check_task_order.sh` 의 `TID_RE` 와 `scripts/merge_task.sh` 의 `T<n>-<slug>` 검사를 못 넘는다).
- 범위: **문서만.** 코드·시험·마이그레이션·설정·의존성은 바꾸지 않는다. 그래서 검증 무게는 CLAUDE.md "도구·CI·문서 — 시험만" 이고 codex 구현 리뷰 대상이 아니다(코드 diff 없음). reviewer 는 문서 대조 한 번.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T9b 병합 | 충족 — master `1643ebc merge: T9b inquiry-home`(트리 = T9b 가지 머리 `78bc275`) | plan.md 3절 T10 행 선행 T9b |
| T9b push · CI | **push 뒤에 잰다.** E-15 는 `merge: T9b` 병합 커밋의 **40자 전체 SHA** 로 CI(push) 실행이 `completed/success` 인지 본다(T9b 결정 xxvi — 빈 SHA 는 gh 가 필터 없음으로 봐 거짓 통과하므로 길이 검사가 먼저). push 전이거나 실행이 끝나지 않았으면 작업 순서 3 을 시작하지 않는다 | T9b 작업 순서 10 |
| 문서 검사 기준선 | 2026-10-24 리드(master `1643ebc`): `bash scripts/check_docs.sh` → `④ 병합된 T: T0a T0b T1 T2a T2b T3 T4 T5 T6 T7 T8 T9a T9b · 대응표 48행 중 대상 48행` · `docs check: OK`. T9b 계획은 "T9b 2행 포함" 이라 적었지만 Q4 ⓑ(결정 xxvii)로 Design 부록 A 에 `test_diagnosis_list_` 행이 더해져 T9b 몫은 3행이다(병합 전 45 → 48) | 이 계획 |
| 새 의존성 | 없다 | — |

## 바뀌는 파일

- [`docs/process/spec.md`](../process/spec.md) (modify): 1절 정본 색인의 "태스크 순서" 행(:38) 상태 칸 `T0a·T0b·T1·T2a·T2b·T3·T4·T5·T6·T7·T8·T9a 병합 · T9b 진행 중` → `T0a·T0b·T1·T2a·T2b·T3·T4·T5·T6·T7·T8·T9a·T9b 병합 · 1차 완료(T10 마감 기록)`.
- [`docs/process/plan.md`](../process/plan.md) (modify): 3절 T9b 행 상태 칸 → "완료. master `1643ebc merge: T9b inquiry-home`"(T9a 행 꼴) · T10 행 상태 `대기` → `완료(이 가지 — 병합하면 1차 끝)` · 착수 조건 칸 `T9b 병합·push` 뒤에 충족 표시.
- [`docs/plans/T9b-inquiry-home.md`](T9b-inquiry-home.md) (modify, 기록 칸만): "최종 E-1~E-15" 행의 E-15 자리 — 작업 순서 3 에서 잰 JSON(`gh run list … --json status,conclusion`)과 `e15-ok` · "병합 뒤 `check_docs.sh` ④ 대상 행 수 · E-15 결론" 행 — ④ 출력 그대로(48행 중 대상 48행) + E-15 결론.
- `docs/plans/T10-phase1-close.md` (new — 이 파일) · okf 목차([`docs/index.md`](../index.md) · [`docs/plans/index.md`](index.md)).

**바꾸지 않는 것:** `src/` · `tests/` · `alembic/` · `scripts/` · `pyproject.toml` · `Makefile` · `CLAUDE.md` · Design · ADR · 다른 태스크 계획(T9b 기록 칸 두 행 밖).

## 작업 순서

1. 리드: 가지 `T10-phase1-close` 를 `1643ebc` 에서 딴다 → 이 파일을 `docs/plans/` 에 두고 okf 네 단계(`okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크 앞뒤 문장 읽기 → `okf index --apply` → `okf check --strict` → `위반 0건 — 통과`) → 이 파일과 목차 둘을 지정해 `plan: T10 phase1-close` 로 커밋(트레일러 없음).
2. 승인자: `approve: T10` 빈 커밋. 그 전에는 아래를 시작하지 않는다.
3. 리드(T9b push 뒤): 아래 E-15 명령을 돌려 `e15-ok` 와 JSON 을 얻는다 → `bash scripts/check_docs.sh` ④ 를 이 가지에서 다시 잰다 → "바뀌는 파일" 의 세 문서를 고친다 → okf 네 단계 → `make okf` → `OKF guard OK` · `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` → `docs check: OK` · `make gate` → `gate: OK` → 세 파일을 지정해 `T10: 1차 마감 문서` 한 커밋.
4. 다른 세션의 reviewer 가 문서 대조(바뀐 글자가 잰 값과 같은지 · 범위 밖 파일 없음)를 하고 "리뷰" 절을 쓴다. Important 0 까지 고친다.
5. `bash scripts/check_task_order.sh` → `task order: OK`. 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T10-phase1-close` → push. **이 병합이 1차의 마지막 병합이다.**

## 위험

| 위험 | 알아채는 법 | 완화 |
|---|---|---|
| T9b 를 push 하기 전이나 CI 가 끝나기 전에 E-15 를 적는다 | E-15 명령이 `e15-ok` 를 내지 않는다(실행 없음 `none` · 진행 중 · 실패) | 작업 순서 3 은 `e15-ok` 가 나온 뒤에만. 실패면 멈추고 승인자에게 보고(CI 실패는 T9b 결함 — T10 이 고치지 않는다) |
| 짧은 SHA·빈 SHA 로 E-15 를 거짓 통과 | 명령의 `test ${#SHA} -eq 40` | T9b 결정 xxvi 의 명령을 그대로 쓴다 |
| 1차 완료 표기를 코드 변경과 섞는다 | `git diff --stat 1643ebc..HEAD` 에 docs 밖 파일 | 바뀌는 파일 넷만 지정 add · reviewer 가 범위를 본다 |
| `merge: T10` 이 check_docs ④ 를 흔든다 | 병합 뒤 ④ 출력 | Design 부록 A 에 T10 행이 없어 T10 대상은 0행(T9b 결정 xxvi) — 병합 뒤 한 번 더 잰다(기록 칸) |

## 증명

```bash
bash scripts/check_task_order.sh                    # → "task order: OK"
SHA=$(git log --first-parent --format=%H --grep='^merge: T9b ' -1 master); test ${#SHA} -eq 40 && test "$(gh run list -b master --commit "$SHA" --workflow ci.yml --event push --json status,conclusion -q 'if length == 0 then "none" else (.[0] | "\(.status)/\(.conclusion)") end')" = completed/success && echo e15-ok   # E-15 → "e15-ok"(push·CI 뒤)
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh                  # → "④ 병합된 T: … T9b · 대응표 48행 중 대상 48행" · "docs check: OK"
okf() { .venv/bin/python scripts/okf/okf.py --root docs --config docs/okf.toml "$@"; }; okf check --strict   # → "위반 0건 — 통과"
make okf                                                                # → "OKF guard OK"
make gate                                                               # → "gate: OK"
git diff --stat 1643ebc..HEAD -- . ':!docs' | tail -1                   # → 빈 출력(docs 밖 변경 없음)
```

## 리뷰

(다른 세션의 reviewer 가 쓴다. Important n건 · Nit n건, 소견과 고친 커밋. Important 0 이 될 때까지 고친다 — r3 §5.1-3)

## 계획과 다르게 한 것

(구현 중 채운다. 비어 있으면 계획대로다.)

- P1. plan 커밋 때 `okf link --apply` 가 T9b 계획의 두 자리(결정 xxvi :76 · 작업 순서 11 :197)에 이 계획으로 가는 링크를 넣었다 — 글자 `docs/plans/T10-phase1-close.md` 를 링크로 바꾼 것뿐이라 T9b 계획을 plan 커밋에 같이 넣었다(뜻 변화 없음).

| 기록 칸 | 값 |
|---|---|
| 승인(approve 커밋 해시) | |
| E-15(`$SHA` 40자 · JSON · `e15-ok`) | |
| `check_docs.sh` ④ — T10 커밋 전·뒤 | 커밋 전(`1643ebc`): 48행 중 대상 48행 · docs check: OK |
| 병합 뒤 ④(`merge: T10` 뒤 master) | |




---

# Resources

- T9b 계획 결정 xxvi · 작업 순서 10·11 · 기록 칸 두 행(저장소 [`docs/plans/T9b-inquiry-home.md`](T9b-inquiry-home.md)).
- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §6 E-15 · 192(gitignore — 저장소 루트 기준 경로).
