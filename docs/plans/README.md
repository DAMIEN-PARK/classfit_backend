---
type: Readme
---

# 태스크 계획 파일 (docs/plans/)

태스크마다 계획을 여기 커밋하고, 승인자가 승인한 뒤에만 코드를 바꾼다. 흐름의 정본은 r3 §5.1 이다.

- 파일명: `T<n>-<slug>.md`. 틀은 `docs/process/templates/task-plan.md`. 번호는 r3 §5.2 의 태스크 표(T0b 뒤에는 `docs/process/plan.md` 의 태스크 순서표)를 따른다.
- 가지 이름은 `T<n>-<slug>` 이고, 계획 파일이 그 가지의 첫 커밋이다.
- 승인자의 `approve: T<n>` 빈 커밋(`Approved-by:` 트레일러)이 첫 `T<n>:` 커밋보다 앞에 있어야 한다. 그 전에는 코드 변경이 없다. 에이전트는 `Approved-by` 를 쓰지 않는다.

  ```bash
  git commit --allow-empty -m "approve: T<n>" -m "Approved-by: DAMIEN-PARK"
  ```

- 계획 줄 `- 승인:` 은 기록용이다. 승인의 증거는 위 approve 커밋이다.

## 커밋 제목 규약

| 제목 | 누가 | 어디에 | 본문 |
|---|---|---|---|
| `plan: T<n> <slug>` | 에이전트 | 가지 첫 커밋. 이 폴더의 계획 파일만 | 트레일러 없음 |
| `approve: T<n>` | 승인자 | 가지. 빈 커밋 | `Approved-by: DAMIEN-PARK` |
| `T<n>: <요약>` | 에이전트 | 가지. approve 뒤 | 트레일러 없음 |
| `sync: T<n> master → <가지>` | 에이전트(`bash scripts/sync_task.sh`) | 가지. master 를 들이는 병합 | 트레일러 없음 |
| `merge: T<n> <slug>` | 승인자(`bash scripts/merge_task.sh`) | master. `--no-ff` 병합 | `make verify` 끝 20줄 + `Approved-by:` |

`bash scripts/check_task_order.sh` 가 이 규약을 잰다. master 는 `scripts/task_order_base` 다음 first-parent 가 전부 `merge:` 여야 한다. 가지는 `plan:` → `approve:` → `T<n>:` 순서여야 하고, `sync:` 병합은 어디에 있어도 된다.

## 병합

- **원격 전:** 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T<n>-<slug>` 를 돌린다. 에이전트 세션은 그동안 멈춘다. 스크립트는 추적 파일 미커밋 변경 0 · 에이전트 정지 확인 · 가지의 `check_task_order.sh` 를 먼저 보고, `git merge --no-ff --no-commit` 뒤 병합 결과에서 `make verify` 를 돌린다. 통과하면 커밋하고, 실패하면 `git merge --abort` 한다. 끝나면 원래 가지로 돌아간다. squash 와 빨리 감기는 쓰지 않는다(`merge.ff=false`).
- **원격 뒤(r3 §1.1 ③ "예"):** PR 로 바꾼다. PR 본문 첫 줄에 계획 파일 경로를 적고(`.github/pull_request_template.md`), 리뷰어는 이 파일과 최종 diff 를 대조한다. master 는 PR 필수 · gates 필수 · 강제 push 금지로 묶는다.

## 계획 안의 절

- **증명:** 명령과 기대 출력. verifier 가 병합 전에 다시 돌린다.
- **리뷰:** 다른 세션의 reviewer 가 쓴다. Important n건 · Nit n건과 소견, 고친 커밋을 적는다. Important 0 이 될 때까지 고친다. 원격 전에는 이 절이 PR 코멘트를 대신한다.
- **계획과 다르게 한 것:** 구현 중 계획과 다르게 한 것을 이유와 함께 적는다. 비어 있으면 계획대로 한 것이다. 병합 전에 채운다.
