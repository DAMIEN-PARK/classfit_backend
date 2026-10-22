---
type: Plan
title: "Plan: ClassFit 마스터 구현 계획"
description: 태스크 한 바퀴 규칙, 1인 레인 A 의 단계, T0a~T9b 13개 태스크의 선행·마이그레이션·착수 조건·증명 요약·상태를 담은 순서표
date: 2026-10-21
tags: [plan, classfit, tasks, sdlc, phase1]
Archives: false
URL: ""
---

# ClassFit 마스터 구현 계획

태스크의 출처는 이 파일 3절이다. T0b 전에는 r3 §5.2 가 출처였고, T0b 에서 이 파일로 옮겼다. 규칙·표·결정은 [Design](2026-10-21-phase1-backend-design.md), 범위는 [feature intent](intents/2026-10-21-phase1-backend.md) 에 있다.

## 1. 규칙

r3 §5.1 "태스크 한 바퀴"다. 커밋 제목 규약은 [태스크 계획 안내](../plans/README.md)에 있다.

1. 태스크는 plan 모드에서 시작한다. 태스크 번호와 이 파일 3절의 행, Design 의 해당 절을 준다.
2. 에이전트가 가지 `T<n>-<slug>` 의 첫 커밋으로 docs/plans 폴더에 계획 파일을 올린다. 틀은 [태스크 계획 틀](templates/task-plan.md)이다. 제목은 `plan: T<n> <slug>` 이고 트레일러는 없다. **이 커밋 전에는 코드 변경이 없다.**
3. 승인자가 계획을 읽고 빈 커밋 `approve: T<n>`(트레일러 `Approved-by: DAMIEN-PARK`)을 더한다. 그 전에는 코드를 바꾸지 않는다. 에이전트는 이 커밋도 트레일러도 쓰지 않는다([agent.md](agent.md) 4절).
4. 구현 커밋 제목은 `T<n>: <요약>` 이다. 다른 세션의 reviewer 가 계획의 "리뷰" 절에 소견을 쓰고, Important 0 이 될 때까지 고친다. verifier 가 계획의 "증명" 명령을 다시 돌린다.
5. 병합은 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T<n>-<slug>` 로 한다. 스크립트는 병합 결과 트리에서 `make verify` 를 돌리고, 통과하면 `merge: T<n> <slug>` 로 커밋한다. squash 와 빨리 감기는 쓰지 않는다.
6. 가지에 master 를 들일 때는 에이전트가 `bash scripts/sync_task.sh` 만 쓴다(제목 `sync: T<n> …`).
7. 계획과 다르게 한 것은 계획 파일의 마지막 절에 이유와 함께 적는다.
8. 원격 `origin` 이 있다. 원격 개통 관문(master 보호 · PR 필수, r3 §5.1 · §1.1 ③)은 아직 닫히지 않았다. 그전에는 5번 뒤 승인자가 master 를 push 한다(T0b 계획 작업 순서 14). 관문이 닫히면 5번이 PR(본문 첫 줄 = 계획 경로) + 승인자 병합으로 바뀐다.
9. 선행 열의 태스크가 병합된 뒤 시작한다. 마이그레이션은 0002~0011 이 한 줄기이고 head 는 하나다(r3 부록 C · §6 E-8). 예외는 T0b 와 T1 이다. 둘은 겹쳐 진행할 수 있다(r3 §3 D2).

## 2. 단계와 레인

| 단계 | 태스크 | 내용 (r3 §3 선택 A2 + D2) |
|---|---|---|
| 문서 | T0a · T0b | SDLC 1~3 + ADR-002·003(T0a), SDLC 4 + OKF 1~7(T0b) |
| 구현 | T1 · T2a · T2b · T3 ~ T8 · T9a · T9b | 위험 순서 관통 슬라이스. 학습자 범위·파일 권한·정원 잠금이 T2b 에서 돌고, 개설 → 입장 → 열람이 T2a·T2b 에서 시연된다 |
| 미룸 | SDLC 5단계 | T4 병합 뒤 착수 가능. 스킬·evals. 배포 게이트·운영 지표는 운영 서버가 정해진 뒤(r3 부록 E 미룸 행) |

- 레인은 **A 하나**다. 승인자 1인 · 저장소 하나 · 작업 트리 하나다(r3 §2 가정 3, §5.1). 승인자가 병합하는 동안 에이전트 세션은 멈춘다.
- 한 태스크 안에서 팀 워커를 나눌 때는 그 계획의 "바뀌는 파일" 머리에 워커별 소유 파일을 적는다. 같은 파일을 두 워커가 고치지 않는다(T0b 계획 전례).
- T0b 와 T1 이 겹치면 문서 커밋과 코드 커밋이 섞인다. 커밋은 파일을 지정해서 한다(r3 §3 D2 단점).

## 3. 태스크 순서표

증명 요약은 r3 §5.2 "관문"이다. 그 T 의 계획 "증명" 절이 명령과 기대 출력을 정한다. 착수 조건은 r3 §1 이고, 기본값으로 진행하는 열린 질문은 [feature intent](intents/2026-10-21-phase1-backend.md) 에 있다.

| T | 제목 | 선행 | 레인 | 마이그레이션 | 착수 조건 | 계획 파일 | 증명 요약 | 상태 |
|---|---|---|---|---|---|---|---|---|
| T0a | SDLC 1~3 + ADR-002·003 | 없음 | A | 없음 | r3 플랜 승인 · r3 §1.1 답(충족) | [T0a-sdlc-bootstrap.md](../plans/T0a-sdlc-bootstrap.md) | `test_hooks.sh` 10/10 OK · `test_gate.sh` 음성 5/5·양성 2/2 OK · trust 수락 기록 · 5.1 한 바퀴 | 완료. master `181006e merge: T0a sdlc-bootstrap` |
| T0b | SDLC 4 + OKF 1~7 | T0a | A | 없음 | pyyaml(dev) 승인 = 이 가지의 approve 커밋(충족) | [T0b-sdlc-okf.md](../plans/T0b-sdlc-okf.md) | `okf check --strict` 위반 0 · `check_docs.sh` OK · 문장 판정 잘못 0 | 완료. master `b14b180 merge: T0b sdlc-okf` |
| T1 | 공통 바닥: 관리자 로그인 · auth_session · auth_attempt · outbox · `issue_email_code()` · stored_file · 파일 Bearer 전달 · `flush_or_conflict` · `Today` · 커서 · 관리 명령 3 · 계약 ② | T0a | A | 0002 | argon2-cffi 승인 = 이 가지의 approve 커밋(충족) · ADR-002·003 병합(충족) | [T1-common-base.md](../plans/T1-common-base.md) | 401 + WWW-Authenticate · 실패 시도는 401 응답 뒤에도 남음 · 다른 클라이언트 주소는 잠금과 무관 · 미등록 owner_kind 404 · 유일 위반 409 · CHECK 위반 500 · 409 요청의 outbox 0행 | 완료. master `74f0441 merge: T1 common-base` |
| T2a | 개설·코드: 빈 강의 개설 + 코드 발급(한 트랜잭션) · 일정·섹션·세션 · 코드 관리 · `course_status_at`·`code_state_at` · golden 추출 | T1 | A | 0003 | 없음 | [T2a-open-course.md](../plans/T2a-open-course.md) | Python·SQL 상태 일치 · 일정 golden · 종료 강의 :resume 409 · KST 경계 시험 | 완료. master `c46660e merge: T2a open-course` |
| T2b | 입장·포털: 입장·재입장 · learner(이메일만)·enrollment(이름·부서) · 포털 · 관리자 첨부(pdf·link) · 파일 열람(`href`) | T2a | A | 0004 | python-multipart 승인 = 이 가지의 approve 커밋(충족) | [T2b-enter-portal.md](../plans/T2b-enter-portal.md) | P3 표 7행(시험 9건) + 재발급 2 + 교차 강의 403 · 다른 강의 등록이 이름을 바꾸지 않음 · 동시성 4(정원 · 재발급 · 재발급 뒤 옛 코드 입장 · 로그인 잠금) | 완료. master `cb5edaa merge: T2b enter-portal` |
| T3 | 강사 가입·승인·서류(약관 판본, 인증 코드 해시, 서류 열람 audit) | T2b | A | 0005 | 없음(새 의존성 없음, 업로드는 T2b 의 python-multipart). 결정 (i)~(xix) 기본값 승인 = 이 가지의 approve 커밋(충족). 서류 시드는 r3 §7-2 기본값(기획안 3종) | [T3-instructor-onboarding.md](../plans/T3-instructor-onboarding.md) | A2 상태 4행 전이 · outbox 에 코드 평문 없음 | 완료. master `4b1fb3b merge: T3 instructor-onboarding` |
| T4 | 과정 풀 · import_ax_catalog(멱등) · `published_catalog()` | T3 | A | 0006 | 없음(새 의존성 없음, 업로드는 T2b 의 python-multipart). 결정 (i)~(xxii) 기본값 승인 = 이 가지의 approve 커밋(충족). import 원본은 외부 JSON 경로 인자이고 저장소에는 합성 표본만 둔다(결정 ii) | [T4-course-pool.md](../plans/T4-course-pool.md) | 공개∧활성만 · 강사 이름 없음(통합) · import 두 번 같음 | 진행 중. 가지 T4-course-pool, 승인됨 1e6d384 |
| T5 | 개설 완성·배정(복제·커리큘럼 시작점, 풀에서 고르기, 배정, 기본 강의안 행 복제) | T4 | A | 0007 | 없음. 메모: 포털에 강사 이름을 넣으면 `test_no_personal_keys_portal` 의 `name` 키 검사와 키 이름을 맞춘다(시안 학습자.html:724, T2b). 배정 후보는 `instructor.status = 'approved'` 이고, 서류는 조건이 아니다(T3 결정 xviii). `pool_course`·`curriculum` 을 가리키는 FK 는 NO ACTION 이어도 된다(T4 결정 xi: 고유 과정·커리큘럼 삭제는 비활성). 기본 강의안 행 복제의 원본은 `pool_course_file`(고유 과정)·`capability_file`(AX 과정별 강사 강의안)·`curriculum_file` 이다. 배정 후보 = `capability` 역참조 + `owner_instructor_id`(기획안 :900), 승인 강사만 | 착수 때 작성 | 미승인 배정 409 · 같은 sha 다른 key · 남의 세션 403 | 대기 |
| T6 | 강사 첨부·강사 화면 | T5 | A | 없음 | 없음. html 열기는 r3 §7-5 기본값(501). 메모: T2b 의 첨부 넣기·지우기(`service/files/attachments.py`)는 course 행 잠금 밖이다(T2b 리뷰 Nit 2). 강사 첨부에서 넣기·지우기도 `lock_course` 로 들일지 정한다. `OWNER_KINDS["instructor_document"]` 는 관리자에게 거짓이다(관리자 열람은 audit 끝점, T3 결정 x). 강사 첨부의 owner_kind 판정은 따로 정한다. 풀 파일 3종(`pool_course_file`·`capability_file`·`curriculum_file`)의 종류를 pdf·link 에서 넓히면 폼 enum(`schemas/pool.py` 의 `PoolFileFormIn.kind` · `app/endpoints/pool_files.py` 의 OpenAPI 폼)과 표의 kind CHECK 5종(`models/pool.py` 파일 칸 믹스인)을 같이 본다(T4 결정 viii) | 착수 때 작성 | html 열기 501 · 교체 뒤 옛 href 404 · 유예 안 바이트는 gc 가 안 지움 · 소유자 행 삭제가 stored_file 행을 같은 트랜잭션에서 지움 | 대기 |
| T7 | 기록·사진 | T6 | A | 0008 | 없음. 사진 공개는 r3 §7-7 기본값(공개 표시 없음) | 착수 때 작성 | 상태 전이표 행마다 시험 · 포털에 기록 칸 없음 | 대기 |
| T8 | 만족도 | T7 | A | 0009 | 없음. 메모: [Design 부록 A](2026-10-21-phase1-backend-design.md) T8 행의 `test_concurrent_` 를 정확한 이름으로 좁힌다(T2b 가 같은 접두를 쓴다) | 착수 때 작성 | 동시성 1(열린 설문) · 1인 1회 · I7 최소 응답 수 · I7·A5 결과에 개인 키·제출 시각 없음 | 대기 |
| T9a | 진단·링크·개설 ③ | T8 | A | 0010 | 없음 | 착수 때 작성 | 회사당 open 1 · 제출 응답에 점수 없음 · score golden | 대기 |
| T9b | 교육 문의·관리자 홈 | T9a | A | 0011 | 없음 | 착수 때 작성 | honeypot 응답 동일 + 0행 · 1분 재제출 200 같은 영수증 · Company 0행 · 확인 메일에 내용 없음 | 대기 |

- 규칙 ↔ 시험 이름의 대응은 [Design 부록 A](2026-10-21-phase1-backend-design.md) 에 있다. 병합된 T 의 행은 `scripts/check_docs.sh` ④ 가 잰다.
- 1차 끝(T9b 병합 뒤)의 수용 기준은 r3 §6 E-1~E-15 다. 개수 기준(E-10·E-12·E-14)은 T9b 기준이고, 태스크마다는 그 T 가 더한 시험만 잰다.




---

# Resources

- 승인된 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §1 · §3 · §5.1 · §5.2 · §6 · 부록 C · 부록 E 미룸 행. 저장소 루트 기준 경로이고, `.omc/` 는 gitignore 라 git 에 남지 않는다.
- SDLC 안내서 `2026-10-06-ai-native-sdlc-porting-guide.md` §6.4 plan 틀(저장소 루트)
