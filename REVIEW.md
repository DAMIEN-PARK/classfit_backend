---
title: Review instructions (ClassFit)
description: reviewer 서브에이전트가 읽는 ClassFit 리뷰 지침 — 3패스(Bugs·Security·Compliance)와 Important 기준, 원격 전 기록 위치
date: 2026-10-21
tags: [review, sdlc, classfit, t0a]
Archives: false
URL: ""
---

# Review instructions (ClassFit)

리뷰는 코드를 쓴 세션과 **다른 세션**의 `reviewer` 서브에이전트가 이 파일로 수행한다. 리뷰어는 승인하지 않는다. 병합은 승인자 DAMIEN-PARK 이 한다.

## Passes

세 패스를 순서대로 돌리고 발견마다 패스를 태그한다.

- **Bugs**: 논리 오류, 깨진 경계 케이스(빈 입력·동시 갱신·재시도 상한), 상태 기계 위반, 트랜잭션 경계, async 오용.
- **Security**: 인증 없는 라우트, 권한 첫 WHERE 누락, 다른 테넌트 데이터 노출, 로그·오류 메시지의 PII, 비밀·주소·도메인 리터럴, 외부로 자료를 보내는 새 경로.
  - 원칙 10: 응답에 개인 식별 키가 없다. 만족도·응답 결과(강사 I7·관리자 A5)의 응답 본문·로그에 이름·이메일·enrollment id·제출 시각이 실리지 않는지 본다(기획안 원칙 10, r3 §4).
  - 파일 key: `stored_file.key` 는 추측할 수 없어야 한다(순번·sha256·원본 파일명에서 만들지 않는다, 같은 sha 다른 key). 열람 범위는 `stored_file.owner_kind` 별로 판정하고, 등록되지 않은 owner_kind 는 404 다(r3 부록 C·T1).
  - 교차 강의 접근: 학습자 토큰은 강의 하나(`auth_session.course_id`)에만 유효하다. 다른 강의의 포털·첨부·설문 경로가 403 인지 본다(ADR-002, r3 T2b).
- **Compliance**: PR 본문 첫 줄의 태스크 계획과 diff 대조 — 바뀐 파일이 계획과 같은가, "증명" 절의 명령이 실행됐고 출력이 PR에 붙어 있는가, 계획과 다른 점이 적혀 있는가. 정책 대조표 준수. 범위 밖 항목이 슬쩍 들어오지 않았는가. 테스트가 약화되지 않았는가(삭제·skip·기대값 완화·픽스처 조작).

## What Important means here

Important는 **동작을 깨거나, 데이터·비밀을 새게 하거나, 정책을 어기는** 발견에만 쓴다. 스타일·이름·주석·순서는 Nit다. Important에는 재현 또는 근거(파일:줄, 실행 결과)를 반드시 붙인다.

## Cap the nits

리뷰당 Nit는 최대 5개. 나머지는 개수만 요약한다("Nit 12건 중 5건 표시").

## Do not report

- 잠금 파일(`requirements*.txt`, `package-lock.json` 등)의 내용. 원본(`*.in`)은 본다.
- 자동 생성 마이그레이션의 형식(내용은 본다).
- CI가 이미 강제하는 것(lint·경계·gate 위반은 CI 실패로 드러난다).
- `docs/plans/**` 의 문장 다듬기.

## How to run

1. 새 세션(작성 세션과 다른 창 또는 worktree)에서 `reviewer` 서브에이전트를 호출하고 PR 번호 또는 브랜치를 준다.
2. 결과를 `gh pr comment <n> --body-file review.md` 로 PR에 남긴다. PR 스레드가 기록이다.
3. 작성 세션이 코멘트를 읽고 수정 push한다. 모든 Important가 닫히면 승인자 DAMIEN-PARK 이 병합한다.

원격 전(지금)에는 PR 이 없다. 원격 전 결과는 계획 파일 `docs/plans/T<n>-<slug>.md` 의 "리뷰" 절에 쓴다(r3 §5.1-3). diff 는 `git diff master...HEAD` 로 보고, 병합은 승인자가 Claude 밖 터미널에서 `scripts/merge_task.sh` 로 한다.

## Monthly tuning

매월 첫 주에 지난달 발견을 훑어 Nit 상한·Do not report를 조정한다. 같은 발견이 2회 나오면 `CLAUDE.md`의 "Things Claude gets wrong"에 한 줄로 옮기고, 에이전트 행동 문제면 `evals/agent/`에 사례 1건을 더한다.




---

# Resources

- SDLC 이식 안내서 §6.5 REVIEW.md 원문: `2026-10-06-ai-native-sdlc-porting-guide.md`(저장소 루트)
- 태스크 한 바퀴·원격 전 리뷰 기록: `.omc/plans/2026-10-21-classfit-phase1-r3.md` §5.1-3
- 원칙 10 원문: `기획/BCTONE_기획안_v3.html` "원칙 13" 표 10행
- 학습자 세션 범위: `docs/process/adr/ADR-002-learner-session.md`
- T0a 계획: `docs/plans/T0a-sdlc-bootstrap.md`
