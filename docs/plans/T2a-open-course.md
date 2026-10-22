---
type: Task Plan
title: "Plan: T2a open-course"
description: 빈 강의 개설 + 초대코드 발급(한 트랜잭션)·일정·섹션·세션·코드 관리·course_status_at·code_state_at(+SQL 판)·golden 추출·깨진 커서 422 와 마이그레이션 0003 을 까는 태스크 계획
date: 2026-10-22
tags: [plan, task, t2a, course, invite-code, schedule, classfit]
Archives: false
URL: ""
---

# Plan: T2a open-course (from plan.md#T2a, 2026-10-22)

- 근거: intent [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · spec 절 [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) §1 수명(초대코드 만료) · §4 0003 행 · §5 규칙 2~5·12~19 · 부록 A T2a 4행 · 태스크 [`docs/process/plan.md`](../process/plan.md) 3절 T2a 행. 그 밖에 [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md)(auth_session.course_id) · r3 §5.2 T2a 행 · §6 E-8·E-12·E-13 · 부록 A1 A3 행 · A2 1·2행 · A4 T2a 3행 · B T2a · C 0003 · D · E9 pre-push 행 · F "UTC 서버에서 날짜 하루 어긋남" 행 · 기획안 v3 5-3·5-4·A3·7절 Course(외부, 미추적).
- 승인: `fa6f57b approve: T2a`(2026-10-22, 기본값 (i)~(viii) 변경 없음, 본문은 트레일러뿐). 순서는 `63e29a8` plan → `fa6f57b` approve → `099e586` sync(T1 병합 `74f0441` 들임, 트리 변화 없음) → 구현 커밋.
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T2a" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.
- 가지 `T2a-open-course` 는 T1 머리에서 딴다. 작성 시점(2026-10-22)의 T1 머리는 `5688f82 T1: 문서 — Design 에 T1 실제 이름 반영` 이고, master 는 `b14b180 merge: T0b sdlc-okf` 다. T1 은 아직 병합 전이다.
- 표기: 〔정함〕은 Design 에 없는 이름·값을 이 계획이 정했다는 뜻이다. Design 이 이름을 준 것은 5절 13·14 의 함수 6개(`open_course`·`issue_invite_code`·`course_status_at`·`code_state_at`·`make_days`·`session_time`), 4절의 표 이름, 5절 17 의 `scripts/golden/extract.mjs`·`tests/fixtures/golden.json` 이다. r3 부록 B 의 경로와 T1 머리 `5688f82` 의 코드 이름(코드는 `24e81c3` 뒤로 바뀌지 않았다)도 그대로 썼다. 그 밖의 파일·함수·칸·상수 이름은 〔정함〕 표시가 없어도 전부 이 계획이 정한 것이다. T1 리뷰 수정으로 T1 이름이 바뀌면 sync 뒤 이 계획을 맞추고 "계획과 다르게 한 것" 에 적는다.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T1 병합 | 대기. 이 가지에는 계획 커밋만 먼저 둔다. **승인(approve)과 구현은 T1 병합 + `sync_task.sh` 뒤가 기본이다.** plan.md 1절 9 의 겹침 예외는 T0b·T1 뿐이라, T1 병합 전에 승인하면 그 예외를 T2a 로 넓히는 결정이 된다 | plan.md 1절 9 · 3절 T2a 행 선행 |
| 새 의존성 | 없다. node 는 r3 E-12·E9 가 이미 전제한 로컬 도구이고 CI 는 쓰지 않으므로 새 승인 거리가 아니다. golden 재추출·대조는 로컬(작업 순서 4 관문 · pre-push)에서만 하고, CI 는 커밋된 `tests/fixtures/golden.json` 을 읽는다. Design 에 없는 새 의존성이 필요해 보이면 멈추고 "승인 필요" 로 보고한다 | plan.md T2a 행 "없음" · r3 N8 · E9 |
| 외부 정본 | golden 원본 `시안/관리자.html` 의 sha256 이 spec 1절 값과 같아야 한다. 다르면 재추출 전에 멈추고 보고한다 | spec 4절 2 |
| 로컬 DB | 0003 은 `course_id` 가 있는 auth_session 행이 있으면 가드로 멈춘다. dev 에 T1 이웃 흐름의 probe-learner 행이 남았으면 T1 계획의 정리 줄로 지운다. 시험 DB 는 세션마다 base 부터 다시 만든다(tests/conftest.py:56) | 위험 "0003 FK" 행 |
| T1 시험 영향 2건 | **(1) 0003 FK 때문에 `tests/contracts/test_api_admins.py::test_admin_create_non_admin_403` 의 준비 단계를 고친다.** 지금은 learner 세션을 `course_id=1` 로 넣어(test_api_admins.py:54-57) FK 위반 23503 이 난다. 시험 픽스처로 연 강의의 id 를 쓰고 단언은 그대로 둔다. **(2) 이름 충돌을 피한다.** T1 의 `test_email_code_generated_only_in_issue_email_code`(tests/integration/test_db_email_code.py:49-54)는 src 에서 `\b_new_code\(` 를 부르는 파일이 email_code.py 하나인지 본다. 그래서 초대코드 생성 도우미는 `_new_invite_code` 로 이름을 달리하고, T1 단언은 고치지 않는다 | CLAUDE.md "실패하는 시험을 skip·삭제로 바꾸지 않는다" |
| golden 이름 처리 | r3 N8·부록 D 와 Design 5절 17 은 "회사명·인명은 가명 토큰으로 바꿔 저장" 이라고 쓴다. 이 계획은 시안 자료를 입력으로 쓰지 않고 합성 사례만 돌린다. 그래서 바꿀 이름이 처음부터 없다. 목적(시안 이름이 저장소에 들어오지 않음)은 같고 방법만 다르다. Design 5절 17 문구를 문서 단계에서 맞춘다 | r3 N8 · Design 5절 17 |
| 기본값으로 진행하는 결정 | 승인자가 approve 전에 바꾸라고 하지 않으면 이대로 간다. **(i) 기간:** course 에 start_on·end_on 을 둔다(상태·만료일의 기준). 일차가 있으면 기간은 첫·끝 일차 날짜를 따르고, 일차를 바꾸는 요청이 같은 트랜잭션에서 고친다. 그때 PATCH 로 기간을 바꾸면 409 다. 개설 때 day_count ≥ 1 이면 기간은 `make_days` 의 첫·끝 날이다. 그래서 start_on 이 토·일이면 첫 평일로 옮겨지고, end_on 은 끝 날이 된다(기획안 A3 "종료일은 일정에서 자동"). **(ii) 만료일:** 발급 때 `end_on + invite_expiry_days(30)` 로 저장하고, 기간이 바뀌어도 따라가지 않는다. 재발급은 옛 행의 만료일·정원을 옮기고 새 행은 active 다. **(iii) 코드 상태:** `code_state_at` 판정 순서는 replaced → stopped(강의 ended) → paused → expired → active 이고, 만료일 당일까지 유효하다. 강의 종료 경계는 "종료일 당일은 running 이고 다음 날부터 ended(today > end_on)" 다. 기획안 5-3 "종료일 도래 시 자동" 을 당일 종료로 읽으면 `≥` 로 바뀌고, 코드 정지와 새 입장 차단도 하루 당겨진다. 정원 마감은 enrollment 를 세는 T2b 몫이다. 종료 강의의 `:pause`·`:reissue` 는 200(상태는 계산상 stopped)이고 `:resume` 만 409 다. **(iv) 계약 ②:** layers 로 바꾸고 `auth | courses | files` 의 서로 독립은 그대로 둔다. 계약 수는 3 이다. rules 가 crud·models 를 부르지 않는 것은 새 계약이 아니라 DB 없는 단위 시험과 리뷰가 본다. **(v) 409·422:** 저장 상태와의 충돌(그 강의에 없는 일차, 일차가 있는데 기간 PATCH, 일차 날짜 순서 어긋남)은 409, 본문 모양 오류는 422 다. 422 를 내는 새 도메인 오류 종류는 만들지 않는다. **(vi) 강의 칸:** 기획안 7절 Course 칸 중 회사 연결(T9a)·배정 강사·커리큘럼 원본(T5)만 빼고, 유형·기수·소개·안내문은 nullable 로 지금 둔다. 세션의 `is_open`·`keywords` 는 plan.md T2a 행 밖의 칸이다. 그래도 T2b 포털(기획안 원칙 5 "공개가 꺼진 세션은 준비 중", `test_portal_locked_`)과 T5 강사 PATCH(r3 부록 B T5 `{desc,keywords,is_open}`)가 쓰므로 0004·0007 의 ALTER 를 줄이려고 지금 둔다. T2a 끝점은 관리자 입력만 받는다. **(vii)** 강의 DELETE 의 "수강생 있으면 409" 는 enrollment 표가 생기는 T2b 가 더한다. **(viii) audit:** plan.md 행에는 없지만 상태를 바꾸는 요청(개설·삭제·보관·상태·코드 재발급·정지·재개·수정)은 audit_log 1행을 같은 트랜잭션에 쓴다(백엔드 안내서 §3.2 "상태를 바꾸는 문은 audit_log 1행", T1 `admin.create` 전례). 일정·섹션·세션 편집은 audit 하지 않는다 | 위험 표 · 기획안 5-3·5-4·7절 |

| 칸 | 2026-10-22 에 확인한 값 (방법) |
|---|---|
| node | `/opt/homebrew/bin/node` v25.5.0 (`command -v node && node --version`) |
| 시안 sha256 | `shasum -a 256 시안/관리자.html` = spec 1절 값 `c14d5e96…81be2` |
| 시안 함수 | 관리자.html:656 `SC_SLOT=50, SC_BREAK=10` · 658 scHm · 659 scM2 · 660 scDay · 663 scLunch · 664 scSkip · 665 scTime · 672 scBySlot · 675 scMakeDays · 1417 genCode(알파벳 32자 `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, 6자). 모두 한 줄 함수다(`grep -n '^function sc'`) |
| T1 부품 | `flush_or_conflict(session, message, *rows)` crud/flush.py:18 · `keyset_page(session, stmt, cursor, limit)` crud/page.py:17(깨진 커서는 `decode_cursor` 의 ValueError, core/cursor.py:22) · `Page[T]` schemas/page.py:8 · `Subject`·`OWNER_KINDS` crud/scope.py:16·31 · `bearer_principal`·`AdminCaller`·`today`·`Today` app/deps.py:56·72·75·79 · `today_kst` core/clock.py:15 · `problem()` app/errors.py:68 · `insert_audit` crud/audit.py:12 · 설정은 `request.app.state.settings`(endpoints/auth.py:32) · 계약 ② independence pyproject.toml:81-86 |
| FK 영향 | `git grep -nE 'course_id=|_row\(' HEAD -- tests`: test_api_admins.py:57(learner, course_id=1 → 고친다) · test_db_auth_session.py:44(admin, course_id=7 → CHECK 가 FK 보다 먼저라 23514 그대로 기대, 위험 표) · probe_routes.py:46(course_id NULL, 영향 없음) |
| pre-push 자리 | `.githooks/pre-push:29` 에 `# T2a: golden 재추출 대조(부록 E9)` 주석만 있다 |

## 바뀌는 파일

레인 A, 워커 하나다. 워커를 나누면 이 머리에 소유 파일을 적는다(plan.md 2절). 경로는 `src/classfit/` 아래 종류 우선 폴더다.

**워커 소유(위 "워커 하나" 와 달리 구현에서 워커 2명으로 나눔 — 사용자 지시 "승인을 몰아서 빠르게" 2026-10-22, T1 전례)**

- worker-a(rules·golden·경계·훅·문서): `service/rules/{__init__,status,schedule,invite}.py` · `scripts/golden/{extract.mjs,check.sh}` · `tests/fixtures/golden.json` · `tests/unit/{test_schedule_rules,test_status_rules,test_import_rules,test_invite_rules}.py` · `pyproject.toml`(계약 ②) · `.githooks/pre-push` · `docs/process/{plan,spec}.md`·Design·`CLAUDE.md` + okf 목차. DB 를 쓰지 않는다(`tests/unit` 만).
- worker-b(DB·규칙 흐름·끝점·시험): `core/config.py` · `alembic/versions/0003_open_course.py` · `models/{course,invite_code,auth,__init__}.py` · `crud/{course,schedule,invite_code,scope}.py` · `service/courses/**` · `schemas/{course,invite_code}.py` · `app/endpoints/{courses,schedule,invite_codes}.py` · `app/routers.py` · `tests/fixtures/courses.py` · `tests/integration/{test_db_course_status,test_db_open_course,test_db_auth_session}.py` · `tests/contracts/{test_api_courses,test_api_schedule,test_api_invite_code,test_api_admin_guard,test_api_admins}.py` · `tests/contracts/expected_paths.txt`. 시험 DB `classfit_test`(`.env` 기본). `classfit_b_test` 는 대조 실험·verifier 몫.
- 공유 파일은 없다(라우터·`models/__init__` 은 B 만). 이 계획 파일은 리드만 고친다. 다른 워커 산출물에 기대는 시험·코드는 그 산출물 커밋 뒤에 커밋한다(T1 편차 ⓐⓑ 교훈): `test_invite_rules.py` 는 B 의 `codes.py` 뒤 7단계로, B 의 5단계 커밋은 A 의 4단계 커밋 뒤로.

**설정**
- `src/classfit/core/config.py` (modify): 칸 `invite_expiry_days = 30`〔정함〕(Design 1절 "초대코드 만료 = 종료일 + 30일", 설정 칸 하나로 바꾼다). `_positive` 검사에 더한다. 기본값이 있어 `missing()` 대상이 아니다(Design 5절 20).

**마이그레이션 · models** — 파일·클래스·칸 이름은 〔정함〕이다(Design 4절은 칸을 태스크 계획에 맡긴다). 열 이름은 PG 예약어 `end`·`desc` 를 피한다.
- `alembic/versions/0003_open_course.py` (new): 리비전 `0003`, down `0002`. 표 5개를 만들고, FK 앞에 `SET LOCAL lock_timeout = '5s'` 와 "course_id 가 있는 auth_session 행" 을 세는 `DO $$ … RAISE EXCEPTION` 가드를 둔다(백엔드 안내서 §3.2). 상태 열은 Text + CHECK(Design 5절 12). downgrade 는 FK 를 먼저 지우고 역순으로 지운다.
- `models/course.py` (new): `course` = `Course`: title · client_name · course_type · cohort · method · hours_per_person(int ≥ 0) · start_on · end_on(CHECK start_on ≤ end_on) · slot_min(기본 50, > 0) · break_min(기본 10, ≥ 0) · intro · notice · status(CHECK prep·running·ended, 기본 prep) · status_manual(기본 false) · archived_at · TimestampMixin. `course_day` = `CourseDay`: course_id(FK CASCADE) · day_no · date · start_time · end_time · lunch_start · lunch_end, U(course_id, day_no), CHECK start_time < end_time · 점심 둘 다 있거나 둘 다 없음. `section` = `Section`: course_id(FK CASCADE) · title · sort · description. `session` = `CourseSession`(`AuthSession`·SQLAlchemy `Session` 과 구별): section_id(FK CASCADE) · title · description · day_no · slot · minutes · time_start · time_end(예외 시각, 둘 다 있거나 없음) · keywords(text[]) · is_open(기본 false, 두 칸은 결정 vi), CHECK 일차 없이 slot 없음.
- `models/invite_code.py` (new): `invite_code` = `InviteCode`: course_id(FK CASCADE) · code(U 전 행) · status(CHECK active·paused·replaced) · expires_on · max_seats(NULL 또는 > 0) · TimestampMixin(created_at = 발급일). 부분 유일 색인 `uq_invite_code_course_live`(course_id) WHERE status <> 'replaced'.
- `models/auth.py` (modify): `AuthSession.course_id` 에 `ForeignKey("course.id")`(ON DELETE 기본 NO ACTION 〔정함〕. 수강생이 있는 강의 삭제는 T2b 가 409 로 먼저 막는다). 독스트링의 "0003 이 더한다" 를 고친다.
- `models/__init__.py` (modify): 새 클래스 5개를 재노출한다.

**service/rules** — 최하위 순수 함수(Design 5절 14). DB·crud·models 를 import 하지 않고, 오늘은 인자로 받는다(5절 15). 파일 이름 〔정함〕.
- `service/rules/__init__.py` (new): 독스트링만.
- `service/rules/status.py` (new): `course_status_at(*, start_on, end_on, status, status_manual, today)` = status_manual 이면 status, 아니면 today > end_on → ended, today ≥ start_on → running, 그 밖 prep(기획안 5-3). `code_state_at(*, code_status, expires_on, course_status, today)` = 결정 (iii) 의 순서.
- `service/rules/schedule.py` (new): `make_days(start, n, start_time, end_time)` = scMakeDays(토·일 건너뜀, 60일 가드 그대로). `session_time(day, slot_min, break_min, siblings, target)` = scTime(예외 시각 우선 · 같은 섹션·일차를 slot 순으로 늘어놓고 "앞 세션 끝 + 휴식" · 점심에 걸리면 점심 뒤로(scSkip) · 그날 끝에서 자름). 같은 slot 은 id 순 〔정함〕. 독스트링에 시안 줄 번호를 적는다.
- `service/rules/invite.py` (new): `INVITE_ALPHABET`(genCode 의 32자) · `INVITE_LENGTH = 6`. T2b 의 형식 검사(혼동 문자 422)도 이 원본을 쓴다(Design 5절 16).

**service/courses** — 단일 진입점(Design 5절 13, CLAUDE.md Rules). 정면 재노출은 없다. 파일 이름 〔정함〕.
- `service/courses/__init__.py` (new): 독스트링만.
- `service/courses/open.py` (new): `open_course(session, body, *, actor, invite_expiry_days)`. course 1행 → day_count ≥ 1 이면 `make_days` 로 course_day 와 기간(start_on·end_on, 결정 i) → `issue_invite_code` → `insert_audit`(`course.open`, 결정 viii). flush 까지만 한다. `insert_course` 는 여기서만 부른다.
- `service/courses/codes.py` (new): `issue_invite_code(session, *, course_id, expires_on, max_seats=None)`. `_new_invite_code()`(`secrets.choice` 로 알파벳 6자. T1 의 `_new_code` 단일 진입 시험과 겹치지 않게 이름을 달리한다, 착수 조건 "T1 시험 영향" (2))를 만들어 `flush_or_conflict(session, message, row)` 로 넣는다. 23505 면 새 행·새 코드로 최대 5번〔정함〕, 그래도 안 되면 Conflict 409. 같은 파일에 `reissue_invite_code`(산 행 UPDATE replaced → flush → issue, r3 부록 B T2a) · `pause_invite_code` · `resume_invite_code`(강의 상태 ended 면 Conflict) · `update_invite_code`. `_new_invite_code` 는 이 파일 밖에서 부르지 않는다.
- `service/courses/days.py` (new): 일차 PUT(1..n 으로 다시 매김, 없어진 일차의 세션은 day_no·slot NULL, 기간 따라감) · 일차 PATCH(날짜 순서가 어긋나면 409, 결정 v)·DELETE(번호는 다시 매기지 않는다, 지운 날의 세션은 "일차 미정") · `schedule_of()`(일차마다 세션 시각을 `session_time` 으로).
- `service/courses/sections.py` (new): 섹션·세션 넣기·고치기·지우기(그 강의에 없는 일차는 409, 다른 강의의 섹션은 404). 일정 쪽을 처음부터 두 파일로 나눠 300줄 상한을 넘지 않게 한다.

**crud** — 첫 인자 session, flush 까지(Design 5절 4). 파일 이름 〔정함〕.
- `crud/course.py` (new): `insert_course` · 읽기 · 고치기 · 지우기 · `list_stmt(subject, status, archived, today)` · `course_status_sql(today)` = CASE status_manual → status, end_on < today → ended, start_on ≤ today → running, 그 밖 prep. 목록 필터는 이 SQL 판, 응답의 status 는 Python 판이다.
- `crud/schedule.py` (new): course_day · section · session 읽기·쓰기.
- `crud/invite_code.py` (new): 산 행 찾기 · replaced 표시 · 상태·칸 바꾸기. 넣기는 codes.py 가 `flush_or_conflict` 로 한다.
- `crud/scope.py` (modify): `course_scope(subject)`〔정함〕. admin 은 `true()`, 나머지는 `false()`(기본 거절). T2b(learner course_id)·T5(강사 배정)가 넓힌다. 강의 목록의 첫 WHERE 다(Design 5절 3).

**schemas** 〔정함〕
- `schemas/course.py` (new): `CourseOpenIn{start: Literal["blank"], title, client_name, course_type?, cohort?, method, hours_per_person, start_on, end_on?, day_count 0~40, day_start, day_end, slot_min, break_min, intro?, notice?}`(day_count 0 이면 end_on 필수, ≥ 1 이면 end_on 을 주면 422) · `CoursePatchIn` · `CourseOut`(status 는 계산값 + status_manual) · `CourseOpenedOut{course, invite_code}` · `StatusSetIn` · `DayIn`·`DaysPutIn`(날짜가 오름차순이 아니면 모양 오류 422, 60개까지)·`DayPatchIn` · `SectionIn`·`SectionPatchIn`·`SectionOut` · `SessionIn`·`SessionPatchIn`·`SessionOut` · `ScheduleOut{days[{day_no, date, start_time, end_time, sessions[{id, section_id, title, slot, start, end}]}], undated[]}`.
- `schemas/invite_code.py` (new): `InviteCodeOut{code, status, state, expires_on, max_seats, issued_at}` · `InviteCodePatchIn{expires_on?, max_seats?}` · `NoticeOut{text}`.

**app** — 전부 `AdminCaller`. r3 부록 B T2a 의 `…` 를 풀어 쓴 경로와 경로 변수 이름은 〔정함〕이다. 상태를 바꾸는 요청은 audit 1행이다(결정 viii. action `course.*`·`invite_code.*`, target `course`·id 글자).
- `app/endpoints/courses.py` (new): `GET·POST /v1/admin/courses`(목록 질의 `status`·`archived`(기본 false)·`cursor`·`limit` 1~100 기본 20 〔정함〕, 깨진 커서는 `keyset_page` 의 ValueError 를 받아 422 problem `violations[{loc: ["query","cursor"]}]`) · `GET·PATCH·DELETE /v1/admin/courses/{course_id}` · `POST /v1/admin/courses/{course_id}:archive`·`:set-status`·`:reset-status`. 오늘은 `Today`.
- `app/endpoints/schedule.py` (new): `PUT /v1/admin/courses/{course_id}/days` · `PATCH·DELETE …/days/{day_no}` · `POST /v1/admin/courses/{course_id}/sections` · `PATCH·DELETE …/sections/{section_id}` · `POST …/sections/{section_id}/sessions` · `PATCH·DELETE /v1/admin/sessions/{session_id}` · `GET /v1/admin/courses/{course_id}/schedule`.
- `app/endpoints/invite_codes.py` (new): `GET·PATCH /v1/admin/courses/{course_id}/invite-code` · `POST …/invite-code:reissue`·`:pause`·`:resume` · `GET …/invite-code/notice`(강의명·기간·코드·만료일 글자 〔정함〕).
- `app/routers.py` (modify): ROUTERS 에 셋을 더한다.

**경계 · 훅 · golden**
- `pyproject.toml` (modify): 계약 ② 를 `type = "layers"` · `containers = ["classfit.service"]` · `exhaustive = true` · `layers = ["auth | courses | files", "rules"]` 로 바꾼다. 이름 `2. service 구성요소: rules 가 맨 아래, 나머지는 서로 모른다` 〔정함〕(결정 iv, Design 5절 14). ①·③ 은 그대로다.
- `scripts/golden/check.sh` (new): node 가 없으면 "미구성: node 가 없어 golden 대조를 못 한다" 로 exit 1 이다. 있으면 `node scripts/golden/extract.mjs | diff - tests/fixtures/golden.json` 을 돌리고, 다르면 diff 를 찍고 exit 1, 같으면 `golden: OK` 를 찍는다. 조용한 건너뜀은 없다.
- `.githooks/pre-push` (modify): 29줄 자리에서 `bash scripts/golden/check.sh` 를 부른다(r3 E9). 검사 본문은 check.sh 한 곳이라 대조 실험과 손 실행도 같은 것을 돈다.
- `scripts/golden/extract.mjs` (new): 첫 줄에서 `process.env.TZ = 'Asia/Seoul'` 로 고정한다. `시안/관리자.html` 에서 상수 줄과 함수 8개 줄(scHm·scM2·scDay·scLunch·scSkip·scTime·scBySlot·scMakeDays)만 이름으로 찾아 `node:vm` 에서 돌린다. 입력은 이 파일이 만든 합성 사례라 사람·회사 이름이 없고, 출력은 사례 id·숫자·날짜(ISO)·시각뿐이다(Design 5절 17. 가명 토큰 대신 합성 사례를 쓰는 이유는 착수 조건 "golden 이름 처리" 행). 키 정렬 · 2칸 들여쓰기 · 끝 줄바꿈 JSON 을 stdout 으로 낸다. 사례 〔정함〕: make_days 9개(월·금·토·일 시작, n 0·1·4·5·10, 월말·연말 넘김) · session_time 10개 이상(13:00~17:00 교시 1~4 · 60/0분 · 09:00~18:00 에 점심 12:00~13:00 · 길이 섞임 90+50 · 예외 시각 · 그날 끝 자름 · 같은 slot 둘 · slot 없음·일차 없음은 null).
- `tests/fixtures/golden.json` (new): 위 출력 그대로. CI 의 golden 원본이다(r3 N8).

**시험** — Design 부록 A T2a 4행의 접두를 모두 쓴다. 파일 이름은 Design 5절 18 규약이고, 접두 뒤 이름은 〔정함〕이다.
- `tests/unit/test_schedule_rules.py` (new): `test_golden_schedule_make_days` · `test_golden_schedule_session_time`(golden.json 의 사례 전부, 사례 수가 0 이면 실패).
- `tests/unit/test_status_rules.py` (new): `test_course_status_dates_prep_running_ended`(시작 전날·당일·종료 당일·다음 날) · `test_course_status_manual_wins` · `test_code_state_stopped_when_course_ended` · `test_code_state_order` · `test_code_state_valid_through_expires_on`.
- `tests/unit/test_invite_rules.py` (new): `test_invite_code_alphabet_excludes_confusables`(32자, 0·O·1·I 없음) · `test_invite_code_generator_shape`(`_new_invite_code` 1000번, 6자 · 알파벳 안).
- `tests/unit/test_import_rules.py` (new): `test_rules_imports_no_db_layers`. `service/rules/*.py` 를 ast 로 읽어, classfit 안에서는 `classfit.core`·`classfit.service.rules` 만 import 하는지 본다. 계약 ② layers 는 rules 가 crud·models 를 불러도 `3 kept` 라서 순수성은 이 시험이 잡는다(결정 iv).
- `tests/integration/test_db_course_status.py` (new): `test_course_status_python_matches_sql`. 기간 위치 5 × (수동 아님 + 수동 3값)을 `open_course` 로 만들고, 오늘 3개(시작일·종료일·종료 다음 날)마다 `course_status_sql` 과 `course_status_at` 을 행마다 대조한다.
- `tests/integration/test_db_open_course.py` (new): `test_courses_open_single_entry`(src 에서 `\binsert_course\(` 호출 파일은 open.py 하나, `\bCourse\(` 직접 생성은 crud/course.py 하나) · `test_invite_code_generated_only_in_issue_invite_code`(`\b_new_invite_code\(` 호출과 `\bInviteCode\(` 직접 생성은 codes.py 하나). 두 시험 모두 `def`·`class` 정의 줄은 빼고 센다 · `test_invite_code_unique_across_all_rows`(replaced 행의 코드도 다시 못 씀, 23505) · `test_invite_code_one_live_per_course`(부분 유일) · `test_invite_code_reissue_marks_old_replaced` · `test_invite_code_retry_on_collision`(정의 모듈 `classfit.service.courses.codes._new_invite_code` 를 monkeypatch, guard 대상 밖).
- `tests/integration/test_db_auth_session.py` (modify): `test_auth_session_learner_unknown_course_violates_fk`(23503) 1건을 더한다. 기존 2건은 그대로다.
- `tests/contracts/test_api_courses.py` (new): `test_courses_open_creates_days_and_one_code`(201, 일차 4 · end_on · active 코드 1 · expires_on = end_on + 30 · audit `course.open` 1) · `test_courses_open_failure_leaves_no_rows`(open.py 의 `issue_invite_code` 를 monkeypatch 해 예외, client_noraise 500, course·course_day·invite_code·audit 0행) · `test_courses_non_admin_403` · `test_courses_invalid_422` · `test_courses_list_bad_cursor_422` · `test_courses_list_keyset_has_more` · `test_courses_list_status_filter_matches_item_status` · `test_course_status_kst_boundary_utc_15`(`dependency_overrides[today]` 에 `today_kst(UTC 14:59)`·`(15:00)`) · `test_course_status_set_status_manual_wins` · `test_course_status_reset_status_date_rule_wins` · `test_courses_patch_period_with_days_409` · `test_courses_archive_hidden_from_default_list` · `test_courses_delete_cascades`.
- `tests/contracts/test_api_schedule.py` (new): `test_schedule_put_days_renumbers_and_period_follows` · `test_schedule_put_days_not_ascending_422` · `test_schedule_patch_day_out_of_order_409`(결정 v) · `test_schedule_delete_day_unsets_sessions` · `test_schedule_session_unknown_day_409` · `test_schedule_session_other_course_section_404` · `test_schedule_times_follow_rules`.
- `tests/contracts/test_api_invite_code.py` (new): `test_code_state_resume_ended_course_409` · `test_code_state_pause_resume_200` · `test_invite_code_reissue_api_old_replaced`(audit `invite_code.reissue` 1) · `test_invite_code_patch_expires_on_and_max_seats` · `test_invite_code_notice_has_code_and_period`.
- `tests/contracts/test_api_admin_guard.py` (new): `test_admin_paths_learner_403_and_no_token_401`. 새 앱의 OpenAPI 에서 `/v1/admin/` 로 시작하는 경로·메서드를 전부 돌며(경로 변수는 1, 본문 없음) learner 토큰이면 403, 토큰이 없으면 401 + `WWW-Authenticate: Bearer` 인지 본다. 끝점을 더하고 `AdminCaller` 를 빠뜨리면 여기서 잡힌다.
- `tests/contracts/test_api_admins.py` (modify): `test_admin_create_non_admin_403` 의 준비 단계만(착수 조건 "T1 시험 영향" (1)).
- `tests/contracts/expected_paths.txt` (modify): 17줄을 더해 정렬된 22줄. 더하는 줄은 `/v1/admin/courses` · `…/{course_id}` · `…/{course_id}/days` · `…/days/{day_no}` · `…/invite-code` · `…/invite-code/notice` · `…/invite-code:pause`·`:reissue`·`:resume` · `…/schedule` · `…/sections` · `…/sections/{section_id}` · `…/sections/{section_id}/sessions` · `…/{course_id}:archive`·`:reset-status`·`:set-status` · `/v1/admin/sessions/{session_id}`.
- `tests/fixtures/courses.py` (new) 〔정함〕: `open_test_course(session, **over)`. 기본값(A사 · 시험 강의)으로 `open_course()` 를 부른다. 시험도 강의를 단일 진입점으로 만든다.

**문서**
- `docs/plans/T2a-open-course.md` (new, 뒤에 modify): 이 계획. 리뷰와 "계획과 다르게 한 것" 을 채운다.
- [`docs/process/plan.md`](../process/plan.md) (modify): T2a 행의 계획 파일 칸을 이 파일로, 상태를 "진행 중. 가지 T2a-open-course, 승인됨 <해시>" 로.
- [`docs/process/spec.md`](../process/spec.md) (modify): 1절 plan.md 행 상태 · 2절 2행·4행의 "예정: T2a + `test_golden_schedule_`" → `tests/unit/test_schedule_rules.py` · `scripts/golden/extract.mjs` · 9행 "예정: T2a + extract.mjs 가명 토큰" → 실제 경로(합성 사례라 이름이 없음) · 10행에 `src/classfit/service/courses/open.py` · 3절 A2-1·A2-2 상태 칸.
- [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) (modify): 1절 초대코드 만료 행에 설정 칸 이름과 결정 (ii) · 5절 13 에 open.py·codes.py 경로 · 5절 14 에 T2a 계약 ② 모양 · 5절 17 의 "가명 토큰" 을 "합성 사례(이름 없음)·TZ 고정" 으로(착수 조건 "golden 이름 처리"). 4절 0003 행과 부록 A 는 표·접두가 그대로라 고치지 않는다.
- `CLAUDE.md` (modify): Rules 경계 줄의 ② 설명(independence → rules 최하위 layers) · Commands 에 golden 재추출 한 줄.
- docs 목차(`okf index` 가 고친다).

바꾸지 않는 것: `alembic.ini`(사용자 미커밋 변경) · `.env` · `0001`·`0002` · T1 시험의 단언(test_api_admins 는 준비 단계만, test_db_auth_session 은 시험 1건 추가만. test_db_email_code 의 단일 진입 단언은 `_new_invite_code` 이름으로 피하고 손대지 않는다) · `tests/conftest.py` · `tests/contracts/conftest.py` · `.claude/**` · `Makefile` · `.github/workflows/ci.yml` · pre-push 밖의 셸 스크립트 · templates · ADR · 미추적 `기획/`·`시안/`(읽기만).

## 작업 순서

커밋은 묶음마다 파일을 지정하고 메시지는 `-F` 파일로 넘긴다. `git add -A`·`git add .`·`git commit -a` 는 쓰지 않는다. 단계마다 관문이 녹색이어야 다음으로 간다.

1. 리드: 가지 `T2a-open-course` 를 T1 머리에서 따고 이 파일을 `docs/plans/` 에 둔다. 이어서 `okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크의 앞뒤 문장을 읽는다(근거 줄 · 문서 절 · 작업 순서 1 · Resources 의 저장소 문서 경로) → `okf index --apply` → `okf check --strict` → `위반 0건 — 통과`. 링크가 들어간 이 파일과 목차 [`docs/index.md`](../index.md) · [`docs/plans/index.md`](index.md) 를 파일 지정해 `plan: T2a open-course` 로 커밋한다. 트레일러는 없다.
2. T1 병합 뒤 에이전트: `bash scripts/sync_task.sh` 로 master(`merge: T1 common-base`)를 들인다(`sync: T2a …`). 병합 전에는 들일 길이 없다(`sync_task.sh` 는 master 만 병합하고, 에이전트의 merge·cherry-pick 은 deny 다). 관문: `bash scripts/check_task_order.sh` → `task order: OK`.
3. 승인자: `approve: T2a` 빈 커밋. 그 전에는 아래를 시작하지 않는다.
4. rules + golden(extract.mjs · check.sh · golden.json). 관문: `bash scripts/golden/check.sh` → `golden: OK` · `TZ=America/Los_Angeles bash scripts/golden/check.sh` → `golden: OK` · `.venv/bin/pytest tests/unit -q` failed·error 0 · `make gate` → `gate: OK`(금지 용어·IP). 커밋 `T2a: service/rules·golden 추출`.
5. 0003 → models → crud → service/courses → 시험 픽스처 → T1 시험 준비 단계 → 통합 시험. 관문: `.venv/bin/alembic heads` → `0003 (head)` · `make migrate` 뒤 `.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/alembic check` → `No new upgrade operations detected.` · `.venv/bin/pytest -q` failed·error 0(T1 시험 포함, 특히 `test_admin_create_non_admin_403` 과 `test_email_code_generated_only_in_issue_email_code`). `alembic check` 는 CHECK·부분 색인 조건을 다 비교하지 않으므로(백엔드 안내서 §7-12) 통합 시험이 잰다. 커밋 `T2a: 0003 마이그레이션·모델·crud·service/courses`.
6. schemas → endpoints → routers → expected_paths → 계약 시험. 관문: `.venv/bin/pytest tests/contracts -q` failed·error 0, 증명 표 8항목 녹색. 커밋 `T2a: 끝점·계약 시험`.
7. 계약 ② + pre-push. 관문: `make lint-imports` → `Contracts: 3 kept, 0 broken.` · `.venv/bin/pytest tests/unit/test_import_rules.py -q` → `1 passed` · `bash -n .githooks/pre-push` 무출력 · `bash scripts/golden/check.sh` → `golden: OK`. 커밋 `T2a: 계약 ② rules 최하위·pre-push golden 대조`.
8. 문서(plan.md · spec.md · Design · CLAUDE.md). 이어서 `okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크의 앞뒤 문장을 읽는다 → `okf index --apply` → `okf check --strict` → `위반 0건 — 통과`. 관문: `make okf` → `OKF guard OK`. 커밋 `T2a: 문서 — plan·spec·Design·CLAUDE.md`(pre-commit guard 가 돈다).
9. `make verify`(파이프 없이) exit 0. 이어서 "증명" 의 명령 · 이웃 흐름 · 대조 실험 6개를 돌리고 기록 칸에 적는다.
10. 다른 세션의 reviewer 가 "리뷰" 절을 쓰고 Important 0 까지 고친다. DB 쓰기·되돌리기 어려운 흐름이라 `verifier` 서브에이전트가 "증명" 을 다시 돌린다(CLAUDE.md 검증 표 · Design 5절 19).
11. `bash scripts/check_task_order.sh` → `task order: OK`. 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T2a-open-course`.

## 위험

| 위험 | 알아채는 법 | 완화 (출처) |
|---|---|---|
| 가지가 T1 머리에서 나와 T1 병합 전에는 `check_task_order` 가 T1 커밋을 규약 밖으로 보고 FAIL 한다(가지 첫 커밋이 `plan: T2a open-course` 가 아님). merge_task ③ 도 같은 이유로 거절한다 | `bash scripts/check_task_order.sh` | 예상된 상태다. T1 이 병합되면 master..가지에 T2a 커밋만 남는다. 병합 전에는 들일 길이 없고, 병합 뒤 `sync_task.sh` 로 T1 리뷰 수정까지 들인다. 그래서 승인·구현은 sync 뒤다(plan.md 1절 6·9) |
| T1 가지에 리뷰 수정이 더 붙어 공유 파일(pyproject.toml · expected_paths.txt · test_api_admins.py · CLAUDE.md · docs)이 갈린다 | sync 병합 충돌 · `git diff master...HEAD` | 구현은 sync 뒤에 시작한다(작업 순서 2·3). T1 이름이 바뀌면 이 계획을 고쳐 "계획과 다르게 한 것" 에 적는다 |
| 상태 판정이 Python 판과 SQL 판에서 갈려 목록 필터와 항목 status 가 어긋난다 | `test_course_status_python_matches_sql` · `test_courses_list_status_filter_matches_item_status` · 대조 실험 1 | 경계는 두 판 모두 "today > end_on → ended, today ≥ start_on → running" 이다. 종료일 당일은 running 이다(결정 iii, 승인자가 당일 종료를 고르면 두 판을 같이 바꾼다). 규칙 원본은 rules 이고 SQL 판은 crud 한 곳이다(Design 5절 16) |
| UTC 서버에서 날짜가 하루 어긋난다(KST 00:00~09:00) | `test_course_status_kst_boundary_utc_15` · T1 `test_today_kst_boundary_utc_15` · 대조 실험 2 | 오늘은 `Today`(today_kst) 한 곳이고 판정 함수는 오늘을 인자로 받는다(Design 5절 15, r3 부록 F) |
| 종료 강의 코드가 :resume 으로 다시 열린다 | `test_code_state_resume_ended_course_409` · 대조 실험 3 | resume 은 `course_status_at` 이 ended 면 Conflict. 입장 쪽 판정은 `code_state_at` 의 stopped(T2b P3) |
| 개설이 반쯤 커밋된다(강의만 있고 코드 없음) | `test_courses_open_failure_leaves_no_rows` | `open_course` 는 flush 까지만, 커밋은 `db()` 한 곳(Design 5절 4·13) |
| 재발급 중 산 코드가 둘이 되거나 옛 코드가 남는다 | `test_invite_code_reissue_marks_old_replaced` · `test_invite_code_one_live_per_course` | UPDATE replaced → flush → INSERT(r3 부록 B T2a). 부분 유일 색인이 둘째 산 행을 23505 로 막는다. 동시 재발급의 FOR UPDATE 와 `test_concurrent_` 는 T2b 다(Design 5절 6). T2a 에서 동시 재발급은 500 이 아니라 409 로 끝난다 |
| 코드 충돌·혼동 문자 | `test_invite_code_unique_across_all_rows` · `test_invite_code_retry_on_collision` · `test_invite_code_alphabet_excludes_confusables` | 전 행 유일 + 새 코드로 최대 5번. 알파벳 원본은 rules/invite.py 하나 |
| 0003 FK 가 T1 시험과 dev 행을 깬다 | 작업 순서 5 의 `pytest -q` · 0003 가드 메시지 | test_api_admins 준비 단계를 실제 강의 id 로(착수 조건 "T1 시험 영향" (1)). 초대코드 도우미 이름을 `_new_invite_code` 로 해서 T1 의 `_new_code` 단일 진입 시험도 그대로 녹색이다((2)). dev 의 course_id 있는 세션 행은 가드가 이름을 대며 멈춘다 |
| admin + course_id 행에서 FK 가 CHECK 보다 먼저 서서 T1 시험이 23503 을 받는다 | `test_auth_session_admin_with_course_violates_check`(23514 기대) | PG 는 CHECK 를 행 넣기 때 재고 FK 는 문장 끝 트리거라 23514 가 먼저다. 빨개지면 멈추고 보고한다(시험을 고치지 않는다) |
| golden 이 실행 기계 시간대에 따라 하루 밀린다(시안 `new Date('YYYY-MM-DD')` 는 UTC 자정, `getDay()` 는 현지) | 작업 순서 4 의 `TZ=America/Los_Angeles bash scripts/golden/check.sh` | extract.mjs 첫 줄에서 TZ 를 Asia/Seoul 로 고정한다 |
| golden 에 시안의 회사명·인명이 들어온다 | `make gate` 금지 용어 · 리뷰가 golden.json 을 읽는다 | 사례는 합성이고 출력은 숫자·날짜·시각뿐이다(Design 5절 17, r3 N8) |
| 관리자 시간 함수와 강사·학습자 시간 함수가 다르다(DEC-002) | spec 3절 DEC-002 행 | golden 원본은 관리자.html 만이다(r3 A4). DEC-002 가 다르게 정해지면 그 태스크가 다시 추출한다 |
| `{course_id}` 가 `5:archive` 를 삼켜 동작 경로가 405·422 가 된다 | 계약 시험의 `:archive`·`:set-status`·`:resume` 호출 · `test_openapi_paths_match_expected_without_probe` | Starlette 는 경로가 맞고 메서드가 다르면 다음 라우트를 계속 찾는다. OpenAPI 경로 글자는 expected_paths 22줄과 같아야 한다 |
| rules 가 crud·models 를 부른다(순수성 깨짐). 계약 ② layers 는 이것을 막지 못해 `3 kept` 그대로다 | `test_rules_imports_no_db_layers`(ast 로 import 검사) · 대조 실험 5 | 계약 ② 는 rules 를 맨 아래에만 둔다. crud·models·database·app 금지는 새 계약 대신 이 단위 시험이 잡는다(결정 iv) |
| golden.json 이 손으로 고쳐지거나 시안이 바뀌어 원본과 갈린다 | `bash scripts/golden/check.sh` exit 1(pre-push) · 대조 실험 6 | 검사 본문은 check.sh 한 곳이다. CI 는 시안이 없어 이 대조를 못 하므로 pre-push 가 막는다(r3 N8) |
| 강의 끝점을 더하며 `AdminCaller` 를 빠뜨린다 | `test_admin_paths_learner_403_and_no_token_401` | `/v1/admin/` 경로를 OpenAPI 에서 모두 뽑아 돈다. 새 경로도 자동으로 들어간다 |
| 기간을 바꿔도 만료일이 그대로라 예상보다 일찍 만료된다 | `test_invite_code_patch_expires_on_and_max_seats` | 결정 (ii). 관리자가 PATCH 로 바꾼다. 다르게 하려면 approve 전에 승인자가 고른다 |
| 끝점 파일이 500줄, service·crud 파일이 300줄을 넘는다 | `make gate`(check_file_size) | 끝점은 courses·schedule·invite_codes 셋, 일정 service 는 처음부터 days·sections 둘로 나눈다. crud/schedule.py 가 300줄에 가까우면 같은 식으로 나누고 "계획과 다르게 한 것" 에 적는다 |
| make_days 의 60일 가드가 긴 일정을 자른다 | `test_golden_schedule_make_days` | day_count 상한 40(평일 40일은 60일 안). 더 긴 일정은 PUT days 로 직접 넣는다 |
| iCloud dataless venv 가 EDEADLK 를 낸다 | `Resource deadlock avoided` | 재시도하고, verifier 는 스크래치 venv 로 잰다(T0a "계획과 다르게 한 것" 10) |

## 증명

r3 §6 의 T2a 몫과 plan.md 증명 요약 4항목이다. E-8·E-12·E-13 은 T2a 시점 값이다.

```bash
bash scripts/check_task_order.sh                    # E-1 T1 병합 + sync 뒤 → "task order: OK"(그 전에는 T1 커밋을 위반으로 찍는다, 위험 1행)
make verify                                         # E-3 exit 0 · "gate: OK" · "All checks passed!" · "Contracts: 3 kept, 0 broken." · "passed"(failed·error·skipped 0) · 마지막 줄 "OKF guard OK"
.venv/bin/lint-imports                              # "Contracts: 3 kept, 0 broken."
.venv/bin/alembic heads                             # E-8 T2a 시점 → "0003 (head)"
.venv/bin/pytest tests/contracts/test_api_openapi.py -q                 # E-13 → "1 passed"(expected_paths 22줄)
bash scripts/golden/check.sh && TZ=America/Los_Angeles bash scripts/golden/check.sh   # E-12 로컬 → "golden: OK" 두 줄
test "$(.venv/bin/pytest tests -q --co -k golden | grep -c '::test_golden_')" -ge 2 && .venv/bin/pytest tests -q -k golden   # E-12 → "2 passed"
for n in test_invite_code_ test_golden_schedule_ test_course_status_ test_code_state_; do grep -rqE "def ${n}[A-Za-z0-9_]*\(" tests || echo "없음 $n"; done; echo table-ok   # 병합 전 check_docs ④ 근사 → "table-ok" 한 줄만
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh                  # 병합 뒤 ④ 대상에 T2a 4행 → "docs check: OK"
```

| # | 관문 (plan.md T2a 행 + r3 부록 B) | 명령 `.venv/bin/pytest <노드> -q` | 기대 |
|---|---|---|---|
| 1 | Python·SQL 상태 일치 | `tests/integration/test_db_course_status.py::test_course_status_python_matches_sql` | `1 passed`. 모든 (강의, 오늘) 쌍이 같다 |
| 2 | 일정 golden | `tests/unit/test_schedule_rules.py` | `2 passed`. make_days·session_time 사례 전부 |
| 3 | 종료 강의 :resume 409 | `tests/contracts/test_api_invite_code.py::test_code_state_resume_ended_course_409` | `1 passed`. type `/problems/conflict`, 코드 status 그대로 |
| 4 | KST 경계 | `tests/contracts/test_api_courses.py::test_course_status_kst_boundary_utc_15` | `1 passed`. 시작 전날 UTC 14:59 → prep, 15:00 → running |
| 5 | 개설 + 코드 발급 한 트랜잭션 | `tests/contracts/test_api_courses.py::test_courses_open_failure_leaves_no_rows` | `1 passed`. 500, course·course_day·invite_code·audit 0행 |
| 6 | 재발급은 옛 행 replaced | `tests/integration/test_db_open_course.py::test_invite_code_reissue_marks_old_replaced` | `1 passed`. 산 행 1 · replaced 1 · 코드 다름 |
| 7 | `:reset-status` 뒤 날짜 규칙 | `tests/contracts/test_api_courses.py::test_course_status_reset_status_date_rule_wins` | `1 passed` |
| 8 | 깨진 커서 422 | `tests/contracts/test_api_courses.py::test_courses_list_bad_cursor_422` | `1 passed`. problem+json, `violations[].loc` = `["query","cursor"]` |

**이웃 흐름 — 실제 호출**(CLAUDE.md "바뀐 동작 1개와 이웃 흐름 2개"). dev DB 에서 `make migrate` 와 `make run` 뒤에 한다. 마지막 줄이 이 흐름이 남긴 dev 행을 한 트랜잭션으로 지운다. 안 지우면 다시 돌릴 때 create_admin 이 같은 아이디로 exit 3 이다. 2026-11-02 는 월요일이라 일차 4개의 끝 날은 2026-11-05 다.

```bash
.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/python -m scripts.create_admin --login-id admin-t2a --apply   # 비밀번호는 getpass 두 번
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/admin/login -H 'content-type: application/json' -d '{"login_id":"admin-t2a","password":"<입력한 값>"}' | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
CID=$(curl -s -X POST localhost:8000/v1/admin/courses -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"start":"blank","title":"AI 활용 기초","client_name":"A사","method":"집체","hours_per_person":16,"start_on":"2026-11-02","day_count":4,"day_start":"13:00","day_end":"17:00"}' | .venv/bin/python -c 'import json,sys; b=json.load(sys.stdin); print(b["course"]["id"], b["course"]["end_on"], b["invite_code"]["state"], file=sys.stderr); print(b["course"]["id"])')   # 바뀐 동작 → stderr 에 "<id> 2026-11-05 active"
curl -s -X POST localhost:8000/v1/admin/courses -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"start":"blank","client_name":"A사"}'   # 422 → problem+json, violations[].loc 에 "title"
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000/v1/admin/courses?cursor=@@" -H "Authorization: Bearer $TOKEN"   # 422(깨진 커서)
/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -c "insert into auth_session (token_hash, principal_type, principal_id, course_id, expires_at) values (encode(sha256('probe-learner-t2a'::bytea), 'hex'), 'learner', 1, $CID, now() + interval '1 hour')"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/v1/admin/courses -H 'Authorization: Bearer probe-learner-t2a'   # 403
curl -s -o /dev/null -w '%{http_code}\n' -X POST "localhost:8000/v1/admin/courses/${CID}:set-status" -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"status":"ended"}'   # 200. 중괄호 필수(zsh 는 `$CID:s` 를 변수 수정자로 읽는다)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "localhost:8000/v1/admin/courses/${CID}/invite-code:resume" -H "Authorization: Bearer $TOKEN"   # 409
/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -v ON_ERROR_STOP=1 -c "delete from audit_log where (target_type = 'course' and target_id = '$CID') or (action = 'admin.create' and target_type = 'admin_account' and target_id in (select id::text from admin_account where login_id = 'admin-t2a')); delete from auth_session where course_id = $CID or (principal_type = 'admin' and principal_id in (select id from admin_account where login_id = 'admin-t2a')); delete from course where id = $CID; delete from auth_attempt where kind = 'admin_login' and subject_hash = encode(sha256('admin-t2a'::bytea), 'hex'); delete from admin_account where login_id = 'admin-t2a'"   # 정리. course 를 지우면 course_day·section·session·invite_code 는 CASCADE 다. 한 -c 의 여러 문장은 한 트랜잭션이다
pkill -f 'uvicorn classfit.main:app' ; /usr/sbin/lsof -nP -iTCP:8000 -sTCP:LISTEN || echo port-free   # make run(Makefile:94 uvicorn --reload) 을 끝낸다. 띄운 터미널이 있으면 거기서 Ctrl-C 해도 된다 → "port-free"
```

**대조 실험**(커밋 뒤 임시 clone 에서만, CLAUDE.md). 실험마다 사본을 따로 만든다: `tmp=$(mktemp -d)` 뒤 `git clone -q --no-hardlinks . "$tmp/c1"` … `"$tmp/c6"`. 사본을 고치고, 원본 `.venv` 와 `PYTHONPATH="$tmp/cN/src"` 로 그 시험만 `--rootdir "$tmp/cN"` 으로 돌려 빨간지 본다. 사본에는 `.env` 가 없으니 `CLASSFIT_TEST_DATABASE_URL` 을 셸 환경 변수로 넘긴다(tests/conftest.py:36 이 셸 환경을 먼저 읽는다).
1. `course_status_sql` 의 `end_on < today` 를 `<=` 로: `test_course_status_python_matches_sql` 이 빨개진다(종료일 당일).
2. `today_kst` 를 `now.astimezone(UTC).date()` 로: `test_course_status_kst_boundary_utc_15` 가 빨개진다.
3. `resume_invite_code` 의 종료 검사를 뺀다: `test_code_state_resume_ended_course_409` 가 빨개진다(200).
4. `session_time` 에서 점심 밀기(scSkip)를 뺀다: `test_golden_schedule_session_time` 이 빨개진다.
5. `service/rules/status.py` 에 `from classfit.crud import course` 한 줄을 더한다: `test_rules_imports_no_db_layers` 가 빨개진다. 같은 사본에서 `lint-imports` 는 `Contracts: 3 kept` 그대로임을 함께 적는다.
6. 사본의 `tests/fixtures/golden.json` 시각 하나를 바꾼다: 사본 루트에서 `bash scripts/golden/check.sh` 가 diff 를 찍고 exit 1 이다. 원본 `시안/` 은 사본에 없으므로 `ln -s "$PWD/시안" "$tmp/c6/시안"` 으로 잇는다.

정리: `rm -rf "$tmp"` 뒤 `git status --short` 가 실험 전과 같다(미추적 `기획/`·`시안/`·`공개홈_v24.html`·`memo.md` 만). 시험 DB 는 다음 실행이 base 부터 다시 만든다.

| 기록 칸 | 값 |
|---|---|
| 착수 조건 결정 (i)~(vii) 변경 여부 (approve 커밋 해시) | 변경 없음. `fa6f57b approve: T2a`(본문은 트레일러뿐) |
| sync 커밋 해시 · `check_task_order` 출력 | `099e586 sync: T2a master → T2a-open-course`(Merge made by the 'ort' strategy, 트리 변화 없음) · `task order: OK`(병합 전 "master..가지 커밋 3개 검사", 구현 뒤 8개 검사도 OK). 중간에 사용자 측 빈 커밋 `4aa81bf` 가 붙어 FAIL 1건이 났다가 걷어냄(편차 4) |
| `make verify` 끝 20줄 | ed47643(2026-10-22, 리드): exit 0 · `gate: OK` · `All checks passed!` · `Contracts: 3 kept, 0 broken.` · 시험 목록 끝 `tests/unit/test_status_rules.py .....` · `============================= 120 passed in 4.50s ==============================` · `OKF_PYTHON=.venv/bin/python bash scripts/okf/guard.sh docs` · `OKF guard OK`(failed·error·skipped 0). verifier 재실행 `120 passed in 4.46s`, 같은 끝 줄. 리뷰 반영 `151e1ee` 뒤(리드, 이 계획 갱신 전 작업 트리): exit 0 · `gate: OK` · `All checks passed!` · `Contracts: 3 kept, 0 broken.` · `121 passed in 4.48s` · `OKF guard OK`; 증명 표 8항목 한 번에 → `9 passed in 1.02s` |
| `alembic heads` · dev `alembic check` | `0003 (head)` · dev `make migrate`(0002 → 0003) 뒤 `No new upgrade operations detected.`(worker-b, verifier `alembic current` → `0003 (head)`). 시험 DB downgrade 0002 → upgrade head → check 도 같은 줄. 0003 가드는 course_id 있는 learner 세션 행 1개에서 행 수를 찍고 멈추며 롤백(0002 유지). dev 에 가드 대상 행 0건 |
| golden 대조(두 시간대) · `-k golden` 출력 | `bash scripts/golden/check.sh` → `golden: OK` · `TZ=America/Los_Angeles …` → `golden: OK` · `--co -k golden` 2 → `2 passed, 118 deselected`. 사례 make_days 9(조건 8 + 60일 가드 1) · session_time 14. TZ 고정 줄을 뺀 사본은 LA 에서 날짜가 하루 밀려 diff 212줄(worker-a 스크래치) |
| 증명 표 8항목 출력 | 노드 8개를 따로 돌려 전부 `passed`(2 는 `2 passed`, 나머지 `1 passed`). 리드 한 번에 돌림 → `9 passed in 1.14s`. `test_api_openapi.py` → `1 passed`(expected_paths 22줄, `LC_ALL=C sort -c` 통과). table-ok 루프 → `table-ok` 한 줄 |
| 이웃 흐름 응답(개설 stderr 줄 · 422 · 422 · 403 · 200 · 409) · `port-free` | dev DB · 127.0.0.1:8000(uvicorn 직접, 준비 확인 `/v1/openapi.json`, 편차 5). create_admin exit 0 → 로그인 200 → 개설 **201** stderr `1 2026-11-05 active`(verifier 재실행 `2 2026-11-05 active`, dev 시퀀스 전진) → title 빠짐 **422** `violations[0].loc` `["body","title"]` → `cursor=@@` **422** loc `["query","cursor"]` "깨진 커서입니다" → probe-learner **403** `/problems/forbidden` "관리자만 할 수 있습니다" → `:set-status` ended **200**(status_manual true) → `:resume` **409** `/problems/conflict`(코드 status 는 active 그대로) → 정리 psql exit 0(`DELETE 3·2·1·1·1`) → `port-free` → 잔여 course·admin-t2a·course_id 세션 0·0·0. worker-c-exp 와 verifier 가 각각 한 번씩, 결과 동일 |
| 대조 실험 6개(빨개진 시험 이름 · check.sh exit 코드) · 정리 뒤 `git status --short` | 임시 clone(ed47643, DB classfit_b_test, 고치기 전 녹색 확인): ① `test_course_status_python_matches_sql`(종료일 당일 행 불일치) exit 1 ② `test_course_status_kst_boundary_utc_15`('prep' == 'running') 1 ③ `test_code_state_resume_ended_course_409`(200 == 409) 1 ④ `test_golden_schedule_session_time`(st-lunch-1200-1300, `_skip_lunch` 호출을 항등으로) 1 ⑤ `test_rules_imports_no_db_layers`(['status.py: classfit.crud.course']) 1 · 같은 사본 `lint-imports --no-cache` → `Contracts: 3 kept, 0 broken.` exit 0 ⑥ golden.json `17:00 → 17:10`(+시안 symlink) → check.sh 가 diff 와 `golden: 다름 — …` 을 찍고 exit 1. worker-c-exp 6개 전부 + verifier 1·3·5·6 재측정(2·4 는 기록 대조) 결과 동일. 정리 뒤 `git status --short` = 미추적 `memo.md`·`공개홈_v24.html`·`기획/`·`시안/` 만 |
| verifier 세션 · 날짜 · 판정 | verifier-t2a(다른 세션) · 2026-10-22 · **PASS**, "빌더 주장과 다른 점 없음". 평문 검사: `203.`·소문자 bctone 0건, `BCTONE` 은 제품명·파일명 맥락 13곳뿐, IPv4(예시·루프백 제외) 0건, golden.json 한글 0 |
| 병합 뒤 `check_docs.sh` ④ 대상 행 수 | 병합 전(ed47643): `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` → ① 11 · ② 5 · ③ 10 · ④ 병합된 T: T0a T0b T1 · 42행 중 대상 9행 · `docs check: OK`. 병합 뒤 값은 다음 태스크에서 |

## 리뷰

reviewer-t2a(다른 세션) · 2026-10-22 · 범위 `git diff master...HEAD`(1fc87af · b9cd906 · 74ee5bb · a9fe2a8 · ed47643, 52파일) · REVIEW.md 3패스 · 시험은 돌리지 않음(verifier 몫). 리드가 미리 받아들인 편차는 Important 로 올리지 않았다.

**Important 1건 → 0건 · Nit 5건(전체 9건 중 5건 표시, 3건 반영 · 1건 T2b 인계 · 1건 편차 기록)**

| # | 등급 | 소견 | 처리 |
|---|---|---|---|
| I-1 | Important(Compliance) | 승인 칸(14행)·기록 칸 10행·"계획과 다르게 한 것" 이 HEAD 에서 비어 있는데 편차가 있다(리드 12건 + `patch_course` 가 days.py · `ScheduleDayOut` lunch 칸 · T1 계획 기록 칸 1줄). REVIEW.md Compliance·r3 §5.1-3 위반이라 병합 전 차단 | **이 계획 갱신 커밋으로 닫음**(승인 칸·기록 칸·편차 1~22). 코드 변경 없음 |
| N-1 | Nit(Bugs) | `codes.py` `issue_invite_code` 가 부분 유일 색인 `uq_invite_code_course_live` 충돌(강의에 이미 산 코드)도 새 코드로 5번 헛되이 재시도하고 409 메시지가 "코드가 겹쳤다" 로 오독됨 | 반영: 제약 이름으로 구분해 산 코드 충돌은 재시도 없이 409, 시험 1건 추가(리뷰 반영 커밋 `151e1ee`, 편차 22. 그 커밋 뒤 `pytest tests/contracts tests/integration -q` → `84 passed`, 바뀐 시험 6건만 → `6 passed`, 새 시험은 ed47643 사본에서 빨강 확인) |
| N-2 | Nit(Bugs) | `:pause`·`:resume` 는 이미 그 상태여도 audit 을 쓰고 `archive` 는 건너뜀 — 멱등 호출의 audit 의미가 둘 | 반영: service 가 "바뀌었는지" 를 돌려주고 끝점이 그때만 audit(archive 쪽으로 통일, 편차 22) |
| N-3 | Nit(Bugs, T2b 인계) | `DELETE /v1/admin/courses/{id}` 는 `auth_session.course_id` FK(NO ACTION) 행이 있으면 23503 → 500. T2b 의 "수강생 있으면 409" 가 enrollment 만 세면 남은 세션 행은 그대로 500 | T2b 계획 결정 (xi) 에 "409 조건 = enrollment ∪ auth_session.course_id 행 또는 삭제 crud 가 세션 행을 먼저 지움" 으로 인계 |
| N-4 | Nit(Compliance) | T2a 가지가 `docs/plans/T1-common-base.md:220`(T1 기록 칸)을 고침 — 계획 "바뀌는 파일" 밖 | 편차 6 에 기록 |
| N-5 | Nit(Bugs) | (a) `resume_invite_code` 가 ended 검사를 `live_code` 앞에 두어 산 코드 없는 종료 강의에서 404 대신 409 (b) 같은 값 PATCH 도 `course.update` audit | 반영: (a) 404 검사 먼저 (b) 실제 바뀐 칸만 audit `fields` 에, 0 이면 audit 없음(편차 22) |

미표시 nit 4건(보류): `check.sh` 의 diff 방향이 계획 문구와 반대(메시지로 설명됨) · `open.py` 방어용 ValueError 두 곳은 schema 가 먼저 막아 닿지 않음 · `_require_day` 409 메시지 문체 불일치 · `test_api_admin_guard.py` 상수 이름 `T2A_ADMIN_OPERATIONS` 가 T1 포함 수.

패스별로 확인하고 문제 없던 것: 트랜잭션 경계(service·crud 에 `commit(` 없음, 커밋은 `deps.py` `db()` 하나) · 재발급 UPDATE → flush → INSERT 와 부분 유일 색인(SAVEPOINT 되돌림이 `old`·`course` 를 만료시키지 않음) · Python/SQL 상태 경계 일치 · `code_state_at` 순서 · `Today` 한 곳 · 커서 422 loc · 동작 경로 22줄 · 일차 PUT 다시 매김·세션 NULL·404/409/422 구분 · PG 예약어 없음 · 0003 한 트랜잭션·SET LOCAL·가드·downgrade 역순·naming_convention 일치 · AdminCaller 24작업 전부 · 첫 WHERE `course_scope` · `secrets` 32자 · audit 1행에 코드 평문 없음 · 픽스처 A사만 · skip/xfail 0 · T1 단언 그대로 · 시험 이름 39개 계획과 일치 · 계약 ② layers exhaustive · 파일 크기(최대 endpoints/courses.py 247줄 · crud/schedule.py 171줄) · 문서 4종 갱신 · `session_time` ↔ scTime 665 줄 단위 대조.

## 계획과 다르게 한 것

리드
1. "레인 A, 워커 하나" 대신 워커 2명(소유는 "바뀌는 파일" 머리) — 사용자 지시 "승인을 몰아서 빠르게", T1 전례. 순서 A 4단계 → B 5단계 → A 7·B 6단계 → A 8단계. 다른 워커 산출물에 기대는 커밋은 그 산출물 뒤에 두어 T1 의 빨강 구간이 생기지 않았다(각 커밋 직후 `git archive` 사본에서 pytest 91 → 117 passed).
2. 승인이 sync 전에 왔다(사용자가 T1 병합 직후 approve). 코드 변경은 sync(`099e586`) 뒤에 시작했으므로 착수 조건 1행의 취지(선행 병합 뒤 시작)는 지켰다.
3. 작업 트리의 iCloud 충돌 사본 ` 2.py` 21개(모두 HEAD 와 바이트 동일)를 내려받아 대조한 뒤 지웠다(위험 표 "iCloud dataless" 행의 변종).
4. 1fc87af 직후 사용자 측 빈 커밋 `4aa81bf approve: T0b` 가 가지에 붙어 `check_task_order` FAIL(규약 밖 제목 1건) → 워커 커밋을 보류하고 사용자가 `git reset --soft HEAD~1` 로 걷어냈다. 구현 커밋은 그 뒤라 이력에 흔적이 없다.
5. 이웃 흐름·대조 실험 6은 리드 대신 worker-c-exp 가 돌렸고 verifier 가 다시 돌렸다. 서버는 `make run`(--reload) 대신 uvicorn 직접 실행, 준비 확인은 `/v1/openapi.json`(main.py:54; `/openapi.json` 은 404).
6. `docs/plans/T1-common-base.md:220` 기록 칸(check_docs ④ 실측 · "CI 결과: origin push 미완")을 이 가지에서 채웠다 — T1 계획이 "다음 태스크에서" 로 미룬 것(리뷰 N-4).

worker-a
7. `tests/unit/test_invite_rules.py` 는 4단계가 아니라 7단계 커밋(B 의 `codes.py::_new_invite_code` 에 기댐).
8. `test_rules_imports_no_db_layers` 는 classfit 안 core·rules 외에 sqlalchemy·psycopg import 도 막고, 상대 import 를 패키지 기준으로 풀어 잰다(계획 54행 "DB 를 import 하지 않는다" 의 DB 쪽).
9. `test_invite_code_generator_shape` 는 6자·알파벳 안 외에 1000개에서 32자 전부 등장·서로 다른 코드 > 990 도 본다(거짓 실패 확률 ≈ 32·(31/32)^6000).
10. golden 사례: make_days 9개 안에 60일 가드 사례(`md-guard-sat-n45` → 42개)를 넣어 위험 표 "day_count 상한 40 은 가드 안" 주장을 함께 잰다. session_time 은 14개.
11. `session_time` 은 시안 그대로 "HH:MM" 글자 쌍을 돌려준다(`ScheduleOut` 의 start·end 는 str). 그날 끝을 넘은 세션은 start > end 가 될 수 있고(st-clip-day-end 18:00-17:00), slot 번호 틈은 무시하고 앞 세션 끝 + 휴식에 붙는다(st-slot-gap). scTime 끝의 교시 번호 계산 줄은 닿지 않아 옮기지 않았다(독스트링). **제품상 바꿀지는 DEC-002·승인자 몫**이며 바꾸면 rules·golden 을 함께 고친다.
12. Design 5절 14 표 칸에는 `auth | courses | files` 를 그대로 쓰지 않고 풀어 썼다(GFM 표에서 백틱 안 `|` 도 칸을 가른다).
13. T1 계획 기록 표에 CI 칸이 없어 CI 결과("origin push 미완")를 check_docs 칸 끝에 붙였다.

worker-b
14. `schemas/course.py`·`schemas/invite_code.py` 를 6단계가 아니라 5단계 커밋에(service/courses 가 입력 모양을 받는다).
15. 상태 도우미 `course_status_of`·`code_state_of` 는 `service/courses/codes.py`(open.py 에 두면 순환 import). 기간 규칙 `patch_course` 는 days.py.
16. `day_start`·`day_end` 는 day_count ≥ 1 일 때만 필수(없으면 422), 0 이면 받지 않아도 된다.
17. 목록 `archived=true` 는 보관한 강의만, 기본 `false` 는 보관하지 않은 강의만.
18. 일차 PUT·PATCH 는 `ScheduleOut` 을 돌려주고(`ScheduleDayOut` 에 lunch_start·lunch_end 추가), DELETE 는 204.
19. 시험 토큰 도우미 `admin_headers`·`learner_headers` 를 `tests/fixtures/courses.py` 에 두고 auth_session 행을 직접 넣는다(로그인 생략).
20. 0003 에 계획에 없는 색인 3(section.course_id · session.section_id · invite_code.course_id)과 CHECK 4(점심 순서 · 세션 예외 시각 순서 · slot ≥ 1 · day_no ≥ 1)를 더했다.
21. 워커 커밋 트레일러는 실행 모델 `Claude Opus 5.5`, 리드 커밋은 `Claude Fable 5.1`.

리뷰 반영
22. (리뷰 반영 커밋 `151e1ee`, 7파일 +125 −47, 리뷰 절 N-1·N-2·N-5) 초대코드 발급의 23505 를 `diag.constraint_name` 으로 구분(`uq_invite_code_course_live` 면 재시도 없이 "이 강의에 산 초대코드가 이미 있습니다" 409, 코드 글자 충돌만 5번 재시도, `crud/flush.py` 는 그대로; 시험 `test_invite_code_issue_when_live_exists_409_no_retry` 추가) · `:pause`·`:resume` 는 (행, 바뀌었는지)를 돌려주고 끝점은 바뀐 때만 audit(archive 와 통일 — 계획 63·80행의 "audit 1행" 과 다름) · resume 은 `live_code` 404 를 ended 409 보다 먼저 · 강의 PATCH(`days.patch_course`)와 초대코드 PATCH(`update_invite_code`) 모두 현재 값과 다른 칸만 쓰고 바뀐 칸이 0 이면 audit 없음(초대코드 PATCH 는 리뷰 범위 밖이지만 멱등 audit 규칙을 하나로 두려고 함께 맞춤). 단언을 더한 기존 시험(완화 없음): `test_code_state_pause_resume_200`(반복 호출 audit 2·1) · `test_code_state_resume_ended_course_409`(산 코드 없으면 404) · `test_invite_code_patch_expires_on_and_max_seats`(같은 값 PATCH audit 없음) · `test_courses_patch_period_with_days_409`(같은 값 PATCH 200, audit fields 는 바뀐 칸만).




---

# Resources

- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §1 · §5.2 T2a 행 · §6 · 부록 A1 · A2 · A4 · B T2a(엔드포인트·시험 세부) · C · D · E9 · F. 저장소 루트 기준 경로이고 `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 저장소 문서: [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) · [`docs/process/plan.md`](../process/plan.md) · [`docs/process/spec.md`](../process/spec.md) · [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md) · [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · [`docs/plans/T1-common-base.md`](T1-common-base.md) · [`docs/plans/T0b-sdlc-okf.md`](T0b-sdlc-okf.md)(형식 본보기).
- 백엔드 안내서 `2026-10-21-backend-framework-porting-guide.md` §3.1(커서·동작 접미사) · §3.2(가드·Text+CHECK) · §3.5(시험) · §7-12(저장소 루트).
- 외부 정본(미추적): `기획/BCTONE_기획안_v3.html` 5-3 강의 상태 기계 · 5-4 초대코드 규칙 · A3 강의 개설·편집 · 7절 Course·Day·InviteCode·Section·Session · `시안/관리자.html` 656-675 · 1417.
- T1 코드(머리 `5688f82`, 2026-10-22): `src/classfit/{core/config.py, core/clock.py, core/cursor.py, crud/flush.py, crud/page.py, crud/scope.py, crud/audit.py, schemas/page.py, app/deps.py, app/errors.py, app/routers.py, app/endpoints/auth.py, models/auth.py}` · `alembic/versions/0002_common_base.py` · `tests/conftest.py` · `tests/contracts/conftest.py` · `tests/contracts/test_api_admins.py` · `tests/contracts/test_api_openapi.py` · `tests/integration/test_db_auth_session.py` · `tests/stale_patch_guard.py` · `pyproject.toml` · `.githooks/pre-push`.
