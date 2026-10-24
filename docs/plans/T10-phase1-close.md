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
- 승인: `6bfb4df approve: T10` 와 `e5d335b approve: T10`(2026-10-24, 승인자 `DAMIEN-PARK`, 둘 다 빈 커밋·트레일러만 — 둘째는 문서 커밋 뒤 같은 명령을 다시 실행한 중복, check_task_order OK 라 그대로 둠 · P5). 순서는 plan `98bd554` → 승인 `6bfb4df` → 문서 `dd1f463` → 승인 `e5d335b` → 리뷰 반영이다.
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
git diff --quiet 1643ebc..HEAD -- . ':!docs' && echo docs-only-ok      # → "docs-only-ok"(exit 1 = docs 밖 변경 · 128 = 틀린 rev, 리뷰 N3)
```

## 리뷰

**reviewer-t10**(다른 세션, 2026-10-24, 범위 `1643ebc..e5d335b` — 트리 = `dd1f463`, 읽기 검토 · REVIEW.md 3패스): **Important 0 · Nit 5.**

- 확인(문제 없음): 범위 — docs 밖 0 · 바뀐 파일 여섯(spec · plan.md · T9b 계획 · 이 계획 · 목차 둘)이 "바뀌는 파일" 과 같고 T9b 계획은 P1 링크 두 자리 + 기록 칸 두 행뿐. E-15 — reviewer 가 직접 잰 `$SHA`(40자 = `origin/master`)·JSON·run id·시각이 기록 칸·T9b :405 와 같고 명령 글자는 T9b 결정 xxvi 그대로. ④ — `48행 중 대상 48행` 일치 · Design 부록 A 의 T9b 행 셋(:185 `test_inquiry_` · :186 `test_admin_home_` · :187 `test_diagnosis_list_`), 병합 전 대상 45 = 48 − 3 이라 "3행" 이 맞다. 승인 `6bfb4df` 빈 커밋·트레일러. spec :38·plan.md :60·:61 이 "바뀌는 파일" 글자·T9a 행 꼴과 같다. P2~P4 타당. 더한 줄에 IP·호스트·이메일·비밀 0.
- N1(Nit) 기록 칸 승인 행이 둘째 `approve: T10`(`e5d335b`, 문서 커밋 뒤)를 적지 않았다 — 승인자가 실행했는지 확인할 것. → 고침: 승인자가 직접 실행했다(이 세션의 승인자 셸 입력 `[T10-phase1-close e5d335b] approve: T10`). 머리 "승인" 줄 · 기록 칸 · P5.
- N2(Nit) 증명 7줄 중 E-15·check_docs 만 기록됐고 `make verify` 가 증명에 없는데 편차에도 없다. → 고침: 기록 칸 "증명 블록 출력" 행 · `make verify` 를 돌려 끝 줄을 적음(P7).
- N3(Nit) 증명 끝 줄 `git diff --stat … | tail -1` 은 git 이 실패해도 빈 출력·exit 0 이라 거짓 통과. → 고침: `git diff --quiet … && echo docs-only-ok`(P7).
- N4(Nit) 낡은 글자 셋 — plan.md 머리말 "T0a~T9b 13개"(표는 T10 포함 14행) · plan.md :64 "1차 끝(T9b 병합 뒤)" · T9b 결정 xxvi(:76)·증명 주석(:278)의 "T9b 2행" 을 :412 정정이 가리키지 않음. → 고침: 셋 다(P6).
- N5(Nit) P4 에 병합 뒤 ④ 의 정확한 글자(`sort -u` 라 `T1 T10 T2a` 순)와 병합 뒤 plan.md :61·spec :38 꼴 갱신이 빠졌다. → 고침: P4 에 더함.
- 고친 커밋: `T10: 리뷰 반영 — 기록 칸 · 증명 · 낡은 글자`(이 갱신). 반영 뒤 Important 0.

## 계획과 다르게 한 것

(구현 중 채운다. 비어 있으면 계획대로다.)

- P1. plan 커밋 때 `okf link --apply` 가 T9b 계획의 두 자리(결정 xxvi :76 · 작업 순서 11 :197)에 이 계획으로 가는 링크를 넣었다 — 글자 `docs/plans/T10-phase1-close.md` 를 링크로 바꾼 것뿐이라 T9b 계획을 plan 커밋에 같이 넣었다(뜻 변화 없음).
- P2. plan.md T10 행은 상태·착수 조건 칸 말고 두 칸을 더 고쳤다 — 증명 요약 "T9b 2행 포함" → "T9b 3행 포함 — Q4 ⓑ"(잰 값, 착수 조건 표의 기준선 행) · 계획 칸 "착수 때 작성" → 이 계획 링크(T9a·T9b 행 꼴). 같은 행 안이고 뜻은 잰 값에 맞춘 것뿐이다.
- P3. `T10: 1차 마감 문서` 커밋은 세 문서에 이 계획(기록 칸 · 편차)을 더한 네 파일이다(위험 표 "바뀌는 파일 넷만"). 목차 둘은 머리말이 그대로라 바뀌지 않았다.
- P4. "병합 뒤 ④" 칸은 `merge: T10` 뒤에는 이 가지에 쓸 수 없다(master 직접 커밋 금지). 병합 뒤 리드가 master 에서 `bash scripts/check_docs.sh` 를 재어 승인자에게 보고하고, 저장소 기록은 2차 첫 태스크 계획이 옮겨 적는다. 예상 줄은 `④ 병합된 T: T0a T0b T1 T10 T2a T2b T3 T4 T5 T6 T7 T8 T9a T9b · 대응표 48행 중 대상 48행` 이다(`scripts/check_docs.sh` :185 가 `sort -u` 라 T10 이 T1 바로 뒤 — Design 부록 A 에 T10 행이 없어 대상 수는 그대로). "대응표 48행 중 대상 48행" 만 대조한다. 같은 2차 첫 태스크가 plan.md :61 T10 상태를 다른 행 꼴 "완료. master `<해시> merge: T10 phase1-close`" 로, spec :38 "(T10 마감 기록)" 을 병합 해시로 고친다 — 병합 뒤 master 에는 "이 가지" 가 없다(리뷰 N5).
- P5. 문서 커밋 `dd1f463` 뒤에 승인자가 같은 승인 명령을 한 번 더 실행해 빈 커밋 `e5d335b approve: T10`(트레일러 `Approved-by: DAMIEN-PARK`)이 생겼다. 트리는 `dd1f463` 과 같다. `scripts/check_task_order.sh` 는 approve 가 구현 커밋보다 앞에 있는지만 보아 `task order: OK` 이고, `scripts/merge_task.sh` 는 approve 수를 세지 않는다. 승인자 커밋이라 에이전트가 지우지 않았다(T3 중복 승인 선례 — [`docs/plans/T3-instructor-onboarding.md`](T3-instructor-onboarding.md) :14 와 같게 기록만, 리뷰 N1).
- P6. 리뷰 N4 — "바뀌는 파일" 이 적은 칸 밖의 낡은 글자 셋을 고쳤다: plan.md 머리말 description "T0a~T9b 13개" → "T0a~T10 14개"(목차 [`docs/process/index.md`](../process/index.md) 는 `okf index --apply` 가 따라 고침) · plan.md :64 를 수용 기준의 시점(T9b 병합 뒤)과 1차 끝(T10 병합)으로 가름 · T9b 기록 칸 :412 정정이 T9b 계획 안의 "2행" 네 자리(결정 xxvi :76 · 바뀌는 파일 :165 · 작업 순서 11 :197 · 증명 주석 :278 — reviewer 는 :76·:278 둘을 짚었고 리드가 grep 으로 넷을 셌다)도 가리키게. 네 자리 본문은 계획 당시(`5c8ee56`) 글자라 두었다.
- P7. 리뷰 N2·N3 — 증명 끝 줄을 `git diff --quiet … && echo docs-only-ok` 로 바꿨다(옛 `--stat | tail -1` 은 rev 가 틀려도 빈 출력·exit 0). 문서 전용이라 증명에 없던 `make verify` 를 리드가 한 번 돌려 기록 칸에 적었다(CLAUDE.md "Verifying your work").

| 기록 칸 | 값 |
|---|---|
| 승인(approve 커밋 해시) | `6bfb4df approve: T10`(`Approved-by: DAMIEN-PARK`, 2026-10-24 — 가지 `T10-phase1-close`, 승인자) · 중복 `e5d335b approve: T10`(문서 커밋 `dd1f463` 뒤, 승인자 재실행 — P5) |
| E-15(`$SHA` 40자 · JSON · `e15-ok`) | 2026-10-24 리드: `$SHA` = `1643ebc0ef2523d3c9ca1e49fc0b02e5ddbc9a6f`(40자) · `[{"conclusion":"success","status":"completed"}]` · `e15-ok`(CI run 40077861625 · 08:23:41 → 08:27:01 UTC) |
| `check_docs.sh` ④ — T10 커밋 전·뒤 | 커밋 전(`1643ebc`): 48행 중 대상 48행 · docs check: OK · 승인 뒤 `6bfb4df`(`CLASSFIT_REQUIRE_EXTERNAL=1`): `④ 병합된 T: T0a T0b T1 T2a T2b T3 T4 T5 T6 T7 T8 T9a T9b · 대응표 48행 중 대상 48행` · `docs check: OK` · 커밋 트리(커밋 직전 작업 트리, `CLASSFIT_REQUIRE_EXTERNAL=1`): 같은 두 줄 |
| 증명 블록 출력(리뷰 반영 커밋 직전 작업 트리, 리뷰 N2) | 2026-10-24 리드: `task order: OK` · `e15-ok` · `④ 병합된 T: T0a T0b T1 T2a T2b T3 T4 T5 T6 T7 T8 T9a T9b · 대응표 48행 중 대상 48행` · `docs check: OK` · `위반 0건 — 통과` · `OKF guard OK` · `gate: OK` · `docs-only-ok`. reviewer-t10 도 `e5d335b` 에서 같은 값(옛 끝 줄 빈 출력) |
| `make verify`(문서 전용이라 증명 밖 — P7) | 2026-10-24 리드(같은 작업 트리, 시험 DB `classfit_c_test`): `gate: OK` · `All checks passed!` · `Analyzed 224 files, 973 dependencies.` · `Contracts: 3 kept, 0 broken.` · `558 passed in 70.52s` · `OKF guard OK` — exit 0(T9b 최종 `a78c373` 과 같은 수) |
| 병합 뒤 ④(`merge: T10` 뒤 master) | (P4 — 병합 뒤 리드가 재어 보고한다) |




---

# Resources

- T9b 계획 결정 xxvi · 작업 순서 10·11 · 기록 칸 두 행(저장소 [`docs/plans/T9b-inquiry-home.md`](T9b-inquiry-home.md)).
- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §6 E-15 · 192(gitignore — 저장소 루트 기준 경로).
