<!-- 원격 개통 전에는 PR 이 없다. 그동안은 `bash scripts/merge_task.sh` 의 병합 커밋 본문(make verify 끝 20줄 + Approved-by)과 계획 파일의 "리뷰"·"계획과 다르게 한 것" 절이 이 본문과 같은 역할을 한다. -->

## 태스크 계획

`docs/plans/T<n>-<slug>.md` — (경로를 첫 줄에 적는다. 계획 없이 만든 변경은 사유를 쓴다)

## 바뀐 것

- 무엇을, 왜. 설계 문서·스펙 절 참조.

## 검증 출력 (`make verify`)

```
(gate · lint · lint-imports · test 출력을 그대로 붙인다. "미구성"도 결과다)
```

## 리뷰어 소견

- `reviewer` 서브에이전트(별도 세션) 결과 요약 또는 PR 코멘트 링크. Important n건 / Nit n건.

## 계획과 다른 점

- 없으면 "없음". 있으면 계획 파일의 마지막 절에도 적었는지 확인.
