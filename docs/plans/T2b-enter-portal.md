---
type: Task Plan
title: "Plan: T2b enter-portal"
description: 수강생 입장·재입장(초대코드 + 이메일)·learner(이메일만)·enrollment(이름·부서)·포털·관리자 첨부(pdf·link)·파일 열람 href·정원·재발급 잠금과 마이그레이션 0004 를 까는 태스크 계획
date: 2026-10-22
tags: [plan, task, t2b, enter, portal, attachment, classfit]
Archives: false
URL: ""
---

# Plan: T2b enter-portal (from plan.md#T2b, 2026-10-22)

- 근거: intent [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · spec 절 [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) §1 수명(수강생 세션 1일 · 초대코드 만료) · §2 수강생 갈래 · §4 0004 행 · §5 규칙 3·6·9·10·11·13·14·18·19 · 부록 A T2b 7행 · 태스크 [`docs/process/plan.md`](../process/plan.md) 3절 T2b 행. 그 밖에 [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md)(결정 1~5) · [`docs/process/adr/ADR-003-external-ports.md`](../process/adr/ADR-003-external-ports.md) · r3 §1(H-3 python-multipart) · §5.2 T2b 행 · §6 E-8·E-10·E-11·E-13·E-14 · 부록 A2 3·4행 · A4 초대코드 검증·파일 접근·준비 중 카드 행 · A5 P3 행 · B T2b · C(0004 · owner_kind 등록 순서 · 소유자 삭제) · D(동시성 픽스처 · 폭발 반경) · F 학습자 사칭·이름 덮어쓰기·무차별 대입·경쟁 행 · 기획안 v3 원칙 5 · 5-4 · P3 · I4 · L1 · 7절(외부, 미추적).
- 승인: `f636ce9 approve: T2b`(2026-10-22, 승인자 `DAMIEN-PARK`, 트레일러만). 결정 (i)~(xiv) 는 기본값 그대로((xiii) 기본 = 로그인 잠금 시험 포함 4 passed · (xiv) 기본 = 입장 무차별 대입 기록 없음). 이 커밋이 python-multipart 추가 승인을 겸했다. 순서는 plan `f047294` → 승인 `f636ce9` → sync `f3fcabc` → 구현 `dbb8706`·`2a90c24`·`7b01baa`·`ddee125`·`3dcc1cf` → 문서 `0118897` → 계획 갱신이다.
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T2b" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.
- 가지 `T2b-enter-portal` 은 T2a 머리에서 딴다. 작성 시점(2026-10-22) T2a 가지 머리는 `a762cb4 T2a: 계획 갱신 — 승인 칸·워커 소유·기록 칸·리뷰 절·계획과 다르게 한 것`(구현 5커밋 `1fc87af`~`ed47643` · 리뷰 반영 `151e1ee` · 계획 갱신), master 는 `74f0441 merge: T1 common-base` 다.
- **이 계획은 T2a 가지 `a762cb4`(코드는 리뷰 반영 `151e1ee`) 기준이다. 커밋이 더 붙으면 plan 커밋 전에 리드가 작업 순서 1 의 대조 명령으로 다시 맞춘다.** 전제한 T2a 이름은 클래스 `Course`·`CourseDay`·`Section`·`CourseSession`·`InviteCode` · `open_course`·`issue_invite_code`·`reissue_invite_code`·`pause_invite_code`·`resume_invite_code`·`update_invite_code`·`schedule_of`·`remove_section`·`remove_session` · `course_status_at`·`code_state_at`·`INVITE_ALPHABET` · `course_scope` · `get_course`·`delete_course`·`get_live_code`·`update_code`·`get_session_and_course`·`list_sections`·`list_sessions` · 픽스처 `open_test_course`·`admin_headers`·`learner_headers` · 끝점 경로다.
- 표기: 〔정함〕은 Design 에 없는 이름·값을 이 계획이 정했다는 뜻이다. Design·r3 가 준 이름은 표 3개(`learner`·`enrollment`·`session_attachment`), 끝점 8개(r3 부록 B T2b), 시험 이름(Design 부록 A T2b 7행), `owner_kind` 값 `session_attachment`(Design 4절)다. 그 밖의 파일·함수·칸·상수·problem type 이름은 〔정함〕 표시가 없어도 전부 이 계획이 정한 것이다.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T2a 병합 | 대기. 이 가지에는 계획 커밋만 먼저 둔다. **승인과 구현은 T2a 병합 + `sync_task.sh` 뒤다.** 겹침 예외는 T0b·T1 뿐이다 | plan.md 1절 9 · 3절 T2b 행 선행 |
| `python-multipart` 추가 | **이 계획의 approve 커밋이 그 승인이다**(T0b pyyaml · T1 argon2-cffi 전례). 런타임 의존성이다. 첫 업로드(관리자 첨부)와 Starlette `request.form()` 이 쓴다 | r3 §1 · H-3 · intent 제약 2 |
| 의존성 추가 절차 | approve 뒤에만 `requirements.in` 에 `python-multipart` 한 줄 → `make lock` → `make install`. 판은 `make lock` 이 정한다(T1 전례, 아래 확인값). deny-deps 훅은 금지 목록만 막아 이 행은 통과하므로 순서는 이 계획이 지킨다. 그 밖의 새 의존성은 없다. `pydantic.EmailStr` 은 `email-validator` 가 필요해 쓰지 않는다(결정 iv) | CLAUDE.md Rules · T1 계획 착수 조건 |
| 외부 정본 | `기획/BCTONE_기획안_v3.html`·`시안/학습자.html` 의 sha256 이 spec 1절 값과 같다(아래 확인값). 다르면 P3 표를 다시 읽기 전에 멈추고 보고한다 | spec 4절 2 |
| 로컬 DB | 0004 는 learner 표가 없던 때의 `auth_session` learner 행(T1·T2a 이웃 흐름의 probe 잔여)이 있으면 가드로 멈춘다. 그 행의 principal_id 가 새 learner id 와 겹치면 남의 세션이 되기 때문이다. T2a 계획의 정리 줄로 지운 뒤 올린다. 시험 DB 는 세션마다 base 부터 다시 만든다(tests/conftest.py:49-63) | 위험 "0004 가드" 행 |
| T2a 시험 영향 | **손대지 않고 녹색이어야 한다.** ① `test_courses_delete_cascades`(test_api_courses.py:374)는 수강생·세션 행·첨부가 없어 새 `remove_course` 의 409·세션 정리·첨부 정리를 지나쳐 그대로 204 다. ② `test_admin_paths_learner_403_and_no_token_401` 은 새 `/v1/admin/` 연산 4개를 OpenAPI 에서 줍는다. 단언이 `>= T2A_ADMIN_OPERATIONS(25)`(test_api_admin_guard.py:17·35)라 29 도 녹색이다. 첨부 POST 는 인증 뒤에 본문을 읽으므로(결정 viii) 403·401 이 그대로다. ③ `test_openapi_paths_match_expected_without_probe` 는 expected_paths 8줄 추가로 맞춘다. ④ 단일 진입 시험(`Course(`·`InviteCode(`·`_new_invite_code(`)을 깨지 않게 src 에서 그 생성자를 부르지 않는다. ⑤ T1 `test_files_unregistered_owner_kind_404` 는 등록부가 비지 않아도 `"unregistered"` 만 본다. ⑥ `learner_headers` 의 가짜 수강생(principal_id 1)은 `LearnerCaller` 가 learner 행을 찾지 않으므로 T2a 시험에서 그대로 쓰인다. 빨개지면 시험이 아니라 코드를 고친다 | CLAUDE.md "실패하는 시험을 skip·삭제로 바꾸지 않는다" |
| 기본값으로 진행하는 결정 | 승인자가 approve 전에 바꾸라고 하지 않으면 이대로 간다. (xiii)·(xiv) 는 기본·대안을 함께 적은 **승인자 선택 항목**이다. **(i) 응답 매핑:** 실패는 problem type 으로 나눈다. 없는 코드와 replaced 코드는 404 `/problems/invite-code-not-found`. 0·O·1·I 가 있으면 422 `/problems/invite-code-confusable`, 그 밖의 형식 오류(길이·문자)는 422 `/problems/invite-code-malformed`. 종료 409 `/problems/course-ended` · 만료 409 `/problems/invite-code-expired` · 정지 409 `/problems/invite-code-paused` · 정원 409 `/problems/course-full`. 새 등록 성공은 201, 재입장은 200, 준비 중은 성공 응답의 `notice` "준비 중인 강의입니다. 시작일 YYYY-MM-DD"(기획안 P3). r3 부록 B 315행 "준비 중은 200 + 안내" 는 2xx 성공(입장 허용)으로 읽는다: lookup 200, 새 등록 201. `POST /v1/enter/lookup` 은 산 코드면 상태와 무관하게 200 + 강의 카드 + `state`(active·preparing·ended·expired·paused·full) + `accepts_new` 를 준다. 시안이 종료 강의 카드를 보여 주고 이메일 재입장을 받기 때문이다(학습자.html:669-676). 404·422 는 두 끝점이 같다. **(ii) 판정 순서:** 형식(혼동 문자 먼저) → 코드로 `course_id` 스칼라만 읽기(ORM 행을 세션에 올리지 않는다) → 강의 행 잠금(`lock_course` 가 None 이면 그 사이 강의가 지워진 것이라 404 `/problems/invite-code-not-found`) → 코드·강의 행을 `execution_options(populate_existing=True)` 로 다시 읽기 → 이 강의에 그 이메일 등록이 있으면 재입장(상태 무관, ADR-002 결정 4) → `code_state_at`(stopped → paused → expired, T2a 결정 iii) → 정원 → 이름 필수(422, `violations[{loc: ["body","name"]}]`). 다시 읽기를 populate_existing 로 하는 이유: SQLAlchemy 는 identity map 에 이미 있는 행의 칸을 덮지 않아(orm/loading.py:1088-1094), 잠금을 기다린 사이 커밋된 replaced·paused 를 못 보고 새 등록을 받는다. 이것을 `test_concurrent_reissue_then_enter_old_code_404` 가 잡는다. 판정은 rules 의 `course_status_at`·`code_state_at` 를 직접 부른다. 계약 ② 때문에 service/courses/codes.py:37·49 의 `course_status_of`·`code_state_of` 는 쓸 수 없다. **(iii) 재입장:** 같은 정규화 이메일 = 같은 learner. 재입장은 들어온 이름·부서를 무시하고 덮지 않는다(P3 "같은 이름으로 이어서"). 다른 강의의 첫 등록은 그 강의 enrollment 에 새 이름·부서를 쓰고 다른 강의 행을 바꾸지 않는다(r3 N9). 재입장마다 새 세션을 주고 옛 세션은 만료까지 산다. 재발급은 세션을 끊지 않는다(5-4). **(iv) 입력 모양:** 이메일은 앞뒤 공백 제거 + 소문자, 254자, 정규식 `^[^@\s]+@[^@\s]+\.[^@\s]+$`. 이름 1~50자, 부서 0~50자 자유 글자(공통 목록은 화면 몫, DEC-016 열림), 셋 다 T1 `no_control_chars`. 코드는 앞뒤 공백 제거 + 대문자(시안 663). **(v) 잠금:** 입장은 `course` 행을 `SELECT … FOR UPDATE` 로 잠근다. 코드 행을 바꾸는 네 문(재발급·정지·재개·수정, codes.py:105·115·126·139)과 강의 삭제 `remove_course` 도 같은 행을 맨 앞에서 잠근다. 재발급 경쟁에서 둘째 요청이 산 코드 행을 잃지 않게, 바뀌는 코드 행이 아니라 고정된 강의 행을 잠근다. 정원은 그 강의 enrollment 수 ≥ 산 코드의 `max_seats` 다. **(vi) 세션:** T1 `create_session` 에 `Principal("learner", learner_id, course_id)` · 수명 `learner_session_days`(1). 응답 `EnterOut{access_token, token_type, expires_at, course_id, name, reentered, notice}`. 수강생 끝점은 새 `LearnerCaller`(아니면 403). **(vii) 포털:** 섹션 → 세션 카드. 카드 `state` 는 `is_open ∧ 첨부 ≥ 1` 이면 open, 아니면 preparing(원칙 5). 잠긴 카드는 제목·일차·시각만 주고 설명·키워드·첨부를 뺀다(DEC-009 열림). 잠긴 세션의 첨부 목록·파일은 403. 종료 강의도 등록자는 200(L1 "종료된 강의도 열람은 된다"). 보관(archived_at)은 관리자 목록 표시만 바꾸고 lookup·입장·포털 판정에는 쓰지 않는다(판정은 강의·코드 상태만). 포털에는 개인 키가 없다(자기 이름도 없음). 관리자 포털은 같은 판정의 미리 보기다. **(viii) 첨부:** kind CHECK 는 기획안 7절 5종(pdf·office·html·link·image)으로 둔다(T6 이 마이그레이션 없이 쓴다). T2b 끝점은 pdf·link 만 받는다. 경로 8개를 지키려고 POST 하나가 폼(multipart·urlencoded) 필드 `kind·title·description?·file|url` 을 받는다. pdf 상한은 설정 `attachment_pdf_max_mb = 50`(기획안 I4). 본문은 인증 뒤에 읽는다: 401 → 403 → 404(세션) → Content-Length 없음 411 · 상한 + 1MiB 초과 413 → 폼 파싱 `async with request.form(max_files=1, max_fields=5) as form`(스풀 파일까지 닫는다. FastAPI 는 자기가 읽은 폼만 닫는다, fastapi/routing.py:455-456) · 파트 수 초과·boundary 없음은 Starlette 가 HTTPException 400 으로 바꿔 `/problems/bad-request`(starlette/requests.py:295-297, app/errors.py:98) → 422(kind·title·url 모양) → 501(pdf 인데 FILE_STORE_ROOT 없음) → 실제 크기 413 → 첫 5바이트 `%PDF-` 아니면 422 → 201. content_type 은 받은 값이 아니라 `application/pdf` 로 고정. link 는 http·https 만, 2048자. 제목 1~200자. sort 는 끝에 붙인다. **(ix) 행 관계:** ERD 대로 `session_attachment.file_id → stored_file`(ON DELETE 기본 NO ACTION). 넣기는 첨부 행 → `stored_file(owner_kind='session_attachment', owner_id=첨부 id)` → `file_id` 채움 순서다. 그래서 CHECK 는 "link ⇔ url 있음 ∧ link 면 file_id 없음" 까지만 걸고 "pdf ⇒ file_id" 는 시험이 잰다. `session_attachment.session_id` 도 NO ACTION 이라, 강의·섹션·세션 삭제 경로가 첨부 행과 그 stored_file 행을 같은 트랜잭션에서 먼저 지운다(r3 부록 C). 섹션·세션은 service/courses/sections.py:43·86 에 더한다. 강의 삭제는 지금 끝점이 crud 를 바로 부르므로(app/endpoints/courses.py:192-198) 새 `service/courses/remove.py::remove_course` 로 옮기고 끝점이 그것을 부른다. 수강생 409 는 규칙이라 service 에 두고, 세 삭제 경로를 service 로 맞춘다. 빠뜨리면 23503 → 500 으로 드러난다. 바이트는 gc 가 지운다. **(x) 범위:** `course_scope` 의 learner 갈래 = `Course.id == subject.course_id`. 목록·조회 crud 는 서명에 subject 를 받고 첫 WHERE 를 `course_scope(subject)` 로 둔다(CLAUDE.md Rules). `OWNER_KINDS["session_attachment"]` = admin 참 · learner 는 같은 강의 ∧ 세션 `is_open` · 그 밖 거짓(T6 이 강사를 넓힌다). **(xi) 강의 DELETE:** enrollment 가 있으면 `remove_course` 가 Conflict 409 를 낸다(T2a 결정 vii). `enrollment.course_id` 도 NO ACTION. 409 조건은 enrollment 만 센다. enrollment 가 없을 때 남은 그 강의의 `auth_session` 행(만료·폐기 세션, probe 잔여)은 같은 트랜잭션에서 먼저 지운다. 이유: 0003 의 `auth_session.course_id` FK 가 NO ACTION 이라, 지우지 않으면 23503 → 500 이다(T2a reviewer nit 3). 1차에는 그 행을 지울 API 가 없으므로, 세션 행까지 409 조건에 넣으면 그 강의를 영영 못 지운다. 강의가 사라지면 그 세션도 쓸 데가 없다. 삭제 순서는 `lock_course`(결정 v. 입장이 강의 행을 잠근 채 등록하는 사이 DELETE 가 잠금 없이 enrollment 0 을 믿고 지우면 23503 → 500 이다) → enrollment 검사 → `auth_session` 행 → 첨부·파일 행(결정 ix) → `delete_course`(CASCADE) 다. **(xii) audit:** 관리자 첨부 넣기·지우기는 audit 1행이다. action `session_attachment.create`·`.delete`, actor `admin:<id>`(T2a `audit_course` 와 같은 꼴, endpoints/courses.py:97), target_type `session_attachment`, target_id 첨부 id 글자, detail `{session_id, kind}`. 입장·재입장·조회는 audit 하지 않는다(enrollment·auth_session 행이 기록이다). **(xiii) 동시성 시험 개수 — 승인자 선택.** 이 태스크의 동시성 시험은 정원 · 재발급 · 재발급 뒤 옛 코드 입장(결정 ii) 셋이 기본이다. intent 바라는 결과 3(intents/2026-10-21-phase1-backend.md:34, "3개")과 r3 §6 E-11("3 passed")은 정원·재발급·열린 설문 셋을 세므로 어느 쪽이든 어긋난다. *기본:* T1 리뷰 nit 2 가 넘긴 로그인 잠금 시험도 `test_db_concurrency.py` 에 둔다. E-11 은 T2b 4 · T8 5 passed 가 된다. 문서 단계에서 intent:34 를 "정원·재발급(2)·로그인 잠금·열린 설문 동시성 시험 5개" 로 고치고, r3 §6 E-11 기대값을 "5 passed" 로 고친다. r3 는 gitignore 라 리드가 따로 고친다. *대안:* 로그인 잠금 시험을 T8 계획에 넘긴다. E-11 은 T2b 3 passed 이고, T8 기대값은 T8 이 정한다. 이때도 intent:34 는 4개 이상이 되어 같이 고친다. **(xiv) 입장 무차별 대입 — 승인자 선택.** 근거는 r3 부록 F "코드·인증 코드 무차별 대입" 행이다. 그 행은 완화를 "시도 기록·차단(§4 수치). 요청 제한은 2차" 라고 쓰지만, §4 수명·만료 표에 초대코드 시도 수치가 없다(로그인 잠금만 있다). *기본:* T2b 는 시도 기록·차단을 두지 않는다. 대응은 코드 공간 32^6 과 재발급이고 요청 제한은 2차다. *대안:* T1 `auth_attempt`·`lock_attempt_key`·`count_recent_failures` 를 재사용한다. 없는 코드·형식 오류 실패를 kind `enter_code` · 클라이언트 주소 기준으로 세고, 같은 (코드, 주소) 또는 주소 하나가 창 안 N회를 넘으면 429 + `Retry-After` 다. 실패 끝점은 T1 처럼 `problem()` 을 반환해 시도 행을 커밋한다. 창·횟수는 승인자가 정하고 Design 1절 표에 더한다 | 위험 표 · 기획안 P3·5-4·I4·L1 |

| 칸 | 2026-10-22 에 확인한 값 (방법) |
|---|---|
| python-multipart | `.venv/bin/pip index versions python-multipart` 최신 0.0.32. 스크래치 폴더에 `pip download`(설치 안 함): `python_multipart-0.0.32-py3-none-any.whl`, Requires-Python ≥3.10, Requires-Dist 없음(이행 의존성 0). `.venv` 의 `import python_multipart` 는 ModuleNotFoundError. 판은 `make lock` 이 정한다 |
| 웹·DB 스택 | Python 3.14.7 · fastapi 0.156.5(requirements.txt:29) · starlette 1.9.0(:74) · sqlalchemy 2.0.55(:70) · alembic 1.20.0(:7). verifier-t2b-plan 확인: FastAPI 는 폼 본문을 의존성보다 먼저 읽는다(fastapi/routing.py:451-475 → 511 solve_dependencies). Starlette 파일 파트는 크기 제한 없이 1MB 넘으면 디스크로 스풀한다(formparsers.py:151·184-192). `on_conflict_do_nothing(index_elements=[func.lower(Learner.email)])` 는 `ON CONFLICT (lower(email))` 로 컴파일된다 |
| 외부 sha256 | `shasum -a 256`: 기획안 `54b8c907…e9d1` · 학습자 `ea336941…7551` = spec 1절 |
| 기획안 줄 | P3 표 7행 기획안_v3.html:393-399 · "코드가 만료돼도 기존 등록자는 재입장" :403 · 부서 공통 목록 :404 · 5-4 "들어올 수 있는 상태는 준비·진행" :338 · 원칙 5 :242 · I4 PDF 50MB :608 · L1 "종료된 강의도 열람은 된다" :682 · 7절 Attachment·Enrollment :909-910(`grep -n`) |
| 시안 줄 | 학습자.html:627 `renderEnter` · :663 대문자화 · :669-676 종료 강의 카드 + 재입장 안내 · :691-698 등록 이메일이면 재입장, 새 이메일은 이름 필수 · :704 `renderPortal` · :720 첨부가 있으면 "강의안 열기", 0 이면 "준비 중" 버튼 · :724 카드의 강사 이름(T5) · :753 `renderGuide` · :786-788 `renderViewer` 의 "준비 중" 잠금 안내 |
| T1 부품 | `create_session`·`Principal` service/auth/sessions.py:37·19 · `learner_session_days` core/config.py:51 · `href_for`·`store_bytes` service/files/store.py:32·37 · `insert_stored_file` crud/stored_file.py:13 · `Subject`·`OWNER_KINDS` crud/scope.py:19·34(a762cb4) · files 판정 app/endpoints/files.py:53-59 · `lock_attempt_key` crud/auth.py:60 · `admin_login` service/auth/login.py:41 · `problem()` app/errors.py:68 · `no_control_chars` schemas/auth.py:14 · `AdminCaller` app/deps.py:72 · id 는 `Identity(always=True)`(models/base.py:35). T1 파일은 a762cb4 까지 config.py 2줄(`invite_expiry_days`) 말고 그대로다 |
| T2a 이름(a762cb4) | crud/course.py `get_course`:27 · `delete_course`:39 · `list_stmt`:54 · crud/invite_code.py `get_live_code`:16 · `update_code`:24 · crud/schedule.py `list_sections`:94 · `delete_section`:103 · `get_session_and_course`:120 · `list_sessions`:133 · `delete_session`:144 · crud/scope.py `course_scope`:37 · service/courses/codes.py `course_status_of`:37 · `code_state_of`:49 · `reissue_invite_code`:105 · `pause`:115 · `resume`:126 · `update`:139. 151e1ee 부터 `pause`·`resume` 은 (행, 바뀌었는지)를, `update` 는 (행, 바뀐 칸 이름 목록)을 돌려준다. `resume` 은 산 코드 404 를 종료 409 보다 먼저 본다 · days.py `schedule_of(session, course)`:117 · sections.py `remove_section`:43 · `remove_session`:86 · rules/status.py :20·38 · rules/invite.py `INVITE_ALPHABET`:8 · 강의 DELETE app/endpoints/courses.py:192-198(crud 직행) · `SessionPatchIn.is_open` schemas/course.py:312 · tests/fixtures/courses.py `open_test_course`:34 · `admin_headers`:61 · `learner_headers`:69 · expected_paths 22줄 · 계약 ② pyproject.toml:82-89. section·session FK 는 CASCADE(models/course.py) |

## 바뀌는 파일

**실행 소유(2026-10-22)**: 계획은 "레인 A, 워커 하나" 였으나 T1·T2a 전례와 사용자 지시("승인을 몰아서 빠르게")대로 워커 2명(opus)으로 나눴다. 리드가 작업 순서 2(sync `f3fcabc`)·4(의존성 `dbb8706`)·10(검증)을 맡았다.
- **worker-a**(5 → 8 → 9): `core/config.py` · `alembic/versions/0004_enter_portal.py` · `models/{learner,attachment,__init__}.py` · `crud/{learner,enrollment,attachment,course,auth,invite_code,scope}.py` · `tests/integration/test_db_enroll.py` → `2a90c24 T2b: 0004 마이그레이션·모델·crud` / `tests/integration/test_db_concurrency.py`(+ test_db_enroll 좁힘) → `ddee125 T2b: 동시성 시험 — 정원·재발급·옛 코드·로그인 잠금`(B 6단계 뒤) / `docs/process/{plan,spec}.md` · Design · intent · `CLAUDE.md` · plans/T0b·T2a 기록 칸 → `0118897 T2b: 문서 — plan·spec·Design·intent·CLAUDE.md`(B 7단계 뒤). 시험 DB `classfit_test`, dev `classfit_dev`.
- **worker-b**(6 → 7): `service/rules/{invite,portal}.py` · `service/enroll/**` · `service/courses/{portal,remove,codes,sections}.py` · `service/files/attachments.py` · `pyproject.toml` 계약 ② · `tests/unit/test_enter_rules.py` → `7b01baa T2b: service — 입장·포털·첨부·잠금, 계약 ② enroll`(A 5단계 뒤) / `schemas/{enter,portal,attachment,enrollment}.py` · `app/deps.py` · `app/endpoints/{enter,portal,attachments,enrollments,courses}.py` · `app/routers.py` · `tests/contracts/expected_paths.txt` · `tests/fixtures/enter.py` · `tests/contracts/test_api_{enter,portal,attachments,enrollments}.py` → `3dcc1cf T2b: 끝점·계약 시험`. 시험 DB `classfit_c_test`(이 태스크에서 새로 만듦).
- **worker-c**(이웃 흐름 · 대조 실험 9, 저장소 무변경) · **verifier-t2b** · **reviewer-t2b**(다른 세션). 다른 워커 산출물에 기대는 커밋은 그 산출물 커밋 뒤에 했다(5 → 6 → 7, 6 → 8, 7 → 9).

원문: 레인 A, 워커 하나다. 나누면 이 머리에 소유 파일을 적고, 다른 워커 산출물에 기대는 시험·기대 파일(expected_paths · 계약 ②)은 그 산출물 커밋 뒤에 커밋한다(T1 리뷰 Important 1). 경로는 `src/classfit/` 아래 종류 우선 폴더다.

**의존성 · 설정**
- `requirements.in` (modify): `python-multipart` 한 줄. `requirements.txt` (modify): `make lock` 산출물, 늘어난 행은 python-multipart 하나여야 한다. `requirements-dev.txt` 는 변경 0 기대.
- `core/config.py` (modify): `attachment_pdf_max_mb: int = 50`(결정 viii), `_positive` 에 더한다. 기본값이 있어 `missing()` 대상이 아니다(Design 5절 20).

**마이그레이션 · models**
- `alembic/versions/0004_enter_portal.py` (new): 리비전 `0004`, down `0003`. `SET LOCAL lock_timeout = '5s'` 와 learner 세션 행을 세는 `DO $$ … RAISE EXCEPTION` 가드 뒤 표 3개를 만든다. downgrade 는 역순.
- `models/learner.py` (new): `learner` = `Learner`: email(Text) · created_at, 유일 색인 `uq_learner_email_lower` = `Index(…, func.lower(email), unique=True)`(r3 부록 C). 이름 칸 없음(ADR-002 결정 2). `enrollment` = `Enrollment`: course_id(FK course) · learner_id(FK learner) · name · dept(NULL) · created_at(= 등록일), U(course_id, learner_id), CHECK `length(btrim(name)) BETWEEN 1 AND 50`. 두 표를 한 파일에 둔다(T1 auth.py · T2a course.py 처럼 한 갈래의 표를 묶는다).
- `models/attachment.py` (new): `session_attachment` = `SessionAttachment`: session_id(FK session) · kind(CHECK 5종) · title · description(NULL) · file_id(FK stored_file, NULL, U) · url(NULL) · sort(int, 기본 0) · TimestampMixin, CHECK `target`(결정 ix), 색인 (session_id, sort, id).
- `models/__init__.py` (modify): 세 클래스를 재노출한다.

**crud** — 첫 인자 session, flush 까지. 목록·조회의 첫 WHERE 는 `course_scope(subject)` 다(결정 x).
- `crud/learner.py` (new): `get_or_create_learner(email)` = `INSERT … ON CONFLICT (lower(email)) DO NOTHING` 뒤 읽기(다른 강의 동시 첫 등록의 23505 를 피한다) · `find_learner(email)`.
- `crud/enrollment.py` (new): `find_enrollment(course_id, learner_id)` · `insert_enrollment` · `count_enrollments(course_id)` · `has_enrollments(course_id)` · `list_stmt(subject, course_id)`(관리자 목록, `course` 조인, 첫 WHERE `course_scope(subject)`, T1 `keyset_page`).
- `crud/attachment.py` (new): 넣기 · `set_file_id` · `list_for_session(subject, session_id)` · `list_for_course(subject, course_id)`(둘 다 session → section → course 조인, 첫 WHERE `course_scope(subject)`, stored_file key·size 조인) · `delete_attachment(id)`(첨부 행 → stored_file 행 순서) · `delete_attachments_under(*, course_id | section_id | session_id)`(결정 ix).
- `crud/course.py` (modify): `lock_course(course_id) -> Course | None` = `select(Course) … with_for_update()` + `populate_existing=True`(잠그면서 새로 읽는다).
- `crud/auth.py` (modify): `delete_course_sessions(course_id) -> int`(그 강의의 `auth_session` 행 전부, 결정 xi).
- `crud/invite_code.py` (modify): `find_course_id_by_code(code) -> int | None`(스칼라, replaced 포함 전 행) · `get_by_code_fresh(code)`(`populate_existing=True`).
- `crud/scope.py` (modify): `course_scope` learner 갈래 · `OWNER_KINDS["session_attachment"]` 판정 함수를 이 파일에 둔다(권한 쿼리는 scope.py 한 곳, Design 5절 3).

**service** — 구성요소 분할의 근거: 계약 ② 는 위층 구성요소끼리 import 를 막는다. 입장은 강의 구성요소의 일정 함수가 필요 없고 세션 발급은 auth 몫이라, 새 구성요소 `enroll` 이 판정만 하고 끝점이 `create_session` 을 잇는다(T1 `admin_login` 처럼 결과 값만 돌려준다). 포털은 `schedule_of` 를 다시 써야 해서 `courses` 안에 둔다. 업로드는 `store_bytes` 와 같은 `files` 안에 둔다. 파일마다 300줄 아래다.
- `service/rules/invite.py` (modify): `parse_invite_input(raw)` → 정규화 코드 또는 `"confusable"`·`"malformed"`(T2a 알파벳 원본을 쓴다, Design 5절 16). `service/rules/portal.py` (new): `card_state(*, is_open, attachments)`.
- `service/enroll/__init__.py` (new, 독스트링만) · `service/enroll/enter.py` (new): `lookup_code(session, *, raw_code, today)` · `enter_course(session, *, raw_code, email, name, dept, today)` → `EnterResult(outcome, learner_id, course_id, name, notice)`. 판정 순서는 결정 (ii)이고, 상태는 rules 의 `course_status_at`·`code_state_at` 를 직접 부르는 작은 도우미로 계산한다(codes.py 의 `course_status_of`·`code_state_of` 는 계약 ② 밖). `insert_enrollment` 은 여기서만 부른다.
- `service/courses/portal.py` (new): `build_portal(session, subject, *, course_id)` · `session_attachments(session, subject, *, session_id)`. 시각은 `schedule_of`, 카드 상태는 `card_state`. 행만 돌려주고 `href` 는 끝점이 단다(schemas 는 service 를 import 할 수 없다).
- `service/courses/codes.py` (modify): `reissue_invite_code`·`pause_invite_code`·`resume_invite_code`·`update_invite_code` 맨 앞에 `lock_course`(결정 v).
- `service/courses/remove.py` (new): `remove_course(session, course_id)` = `lock_course`(결정 v) → `has_enrollments` 면 Conflict 409 → `delete_course_sessions` → `delete_attachments_under(course_id=…)` → `crud.course.delete_course`(결정 ix·xi).
- `service/courses/sections.py` (modify): `remove_section`(:43)·`remove_session`(:86) 이 지우기 전에 `delete_attachments_under`.
- `service/files/attachments.py` (new): `add_pdf_attachment(session, *, root, max_bytes, session_id, title, description, data, actor)`(`asyncio.to_thread(store_bytes)` → 결정 ix 순서 → audit) · `add_link_attachment` · `delete_attachment`.

**schemas** 〔정함〕
- `schemas/enter.py` (new): `EnterLookupIn{code}` · `EnterIn{code, email, name?, dept?}`(이메일 정규화는 AfterValidator) · `EnterLookupOut{course{title, start_on, end_on, status}, state, accepts_new, notice}` · `EnterOut`.
- `schemas/portal.py` (new): `PortalOut{course{id, title, start_on, end_on, status, intro, notice}, sections[{id, title, description, sessions[{id, title, day_no, date, start, end, state, description?, keywords?, attachments[]}]}]}`. `name`·`email`·`dept` 칸이 없다.
- `schemas/attachment.py` (new): `AttachmentOut{id, kind, title, description, href, size}`(pdf 는 `href_for(key)`, link 는 url) · `AttachmentFormIn`(폼 검증용).
- `schemas/enrollment.py` (new): `EnrollmentOut{id, name, dept, email, enrolled_at}`(관리자 전용).

**app**
- `app/deps.py` (modify): `require_learner` · `LearnerCaller`.
- `app/endpoints/enter.py` (new): `POST /v1/enter/lookup` · `POST /v1/enter`(인증 없음, `Today`). 실패는 `problem()` 을 반환한다.
- `app/endpoints/portal.py` (new): `GET /v1/learner/courses/{course_id}/portal`(LearnerCaller, 자기 강의가 아니면 403) · `GET /v1/admin/courses/{course_id}/portal`(AdminCaller). 두 경로가 응답 조립 함수 하나를 써서 한 파일이다.
- `app/endpoints/attachments.py` (new): `GET /v1/learner/sessions/{session_id}/attachments` · `POST /v1/admin/sessions/{session_id}/attachments`(폼 매개변수를 선언하지 않고 의존성 뒤 `async with request.form(…)` 로 읽는다. OpenAPI 는 `openapi_extra` 로 multipart 모양을 적는다) · `DELETE /v1/admin/attachments/{attachment_id}`(204).
- `app/endpoints/enrollments.py` (new): `GET /v1/admin/courses/{course_id}/enrollments`(커서·limit 은 T2a 목록과 같다, 깨진 커서 422).
- `app/endpoints/courses.py` (modify): 강의 DELETE(:192-198)가 `crud_course.delete_course` 대신 `remove_course` 를 부른다. 404·audit 은 그대로다(결정 ix·xi).
- `app/routers.py` (modify): ROUTERS 에 넷을 더한다.

**경계**
- `pyproject.toml` (modify): 계약 ② layers(pyproject.toml:86-89)를 `["auth | courses | enroll | files", "rules"]` 로. 계약 수 3 그대로. exhaustive 라 `service/enroll` 을 만드는 커밋에 같이 넣는다.

**시험** — Design 부록 A T2b 7행. 함수 이름의 접두 뒤는 〔정함〕. E-10 은 `test_api_enter.py` 에서 `::test_(p3|reissue|cross_course|enrollment_name)_` 를 **정확히 13개** 센다. 그래서 그 넷 접두는 이 파일의 13건에만 쓰고 parametrize 하지 않는다. T6 접두 `test_attachment_`·`test_gc_` 는 쓰지 않는다(T6 행 검사가 거짓 녹색이 된다).
- `tests/contracts/test_api_enter.py` (new): `test_p3_active` · `test_p3_preparing` · `test_p3_ended` · `test_p3_expired` · `test_p3_paused` · `test_p3_full` · `test_p3_not_found` · `test_p3_existing_email` · `test_p3_confusable` · `test_reissue_old_code_not_found` · `test_reissue_keeps_sessions` · `test_cross_course_portal_403` · `test_enrollment_name_isolated` + `test_enter_new_email_requires_name_422` · `test_enter_malformed_code_422` · `test_enter_invalid_email_422` · `test_enter_session_lifetime_one_day` · `test_enter_lookup_hides_personal_fields`(E-14 의 `-k no_personal_keys` 에 걸리지 않는 이름).
- `tests/contracts/test_api_portal.py` (new): `test_portal_locked_when_closed` · `test_portal_locked_when_no_attachment` · `test_portal_locked_attachments_403`(목록·href 둘 다) · `test_no_personal_keys_portal`(수강생·관리자 포털과 첨부 목록 응답을 재귀로 훑어 `email·name·dept·learner_id·enrollment_id` 키 0. `name` 은 T5 가 강사 이름을 포털에 넣을 때 걸린다, 문서 절 plan.md T5 메모) · `test_portal_ended_course_existing_learner_200` · `test_portal_times_match_admin_schedule` · `test_learner_paths_admin_403_and_no_token_401`(OpenAPI 의 `/v1/learner/` 경로 전부).
- `tests/contracts/test_api_attachments.py` (new): `test_admin_attachment_pdf_upload_201`(stored_file 1행 · owner 일치 · file_id 채움 · 관리자 href 200 같은 바이트) · `test_admin_attachment_link_201` · `test_admin_attachment_not_pdf_422` · `test_admin_attachment_link_scheme_422`(`javascript:`·`ftp:`) · `test_admin_attachment_too_large_413`(`attachment_pdf_max_mb=1`) · `test_admin_attachment_without_length_411` · `test_admin_attachment_bad_multipart_400`(boundary 없음) · `test_admin_attachment_store_root_unset_501` · `test_admin_attachment_delete_removes_file_row` · `test_admin_attachment_owner_delete_removes_file_rows`(세션·섹션·강의 삭제 뒤 그 첨부의 stored_file 0행).
- `tests/contracts/test_api_enrollments.py` (new): `test_admin_enrollments_list_keyset` · `test_admin_enrollments_bad_cursor_422` · `test_courses_delete_with_enrollments_409` · `test_courses_delete_clears_course_sessions`(enrollment 없는 강의에 T2a `learner_headers` 세션 1 + 폐기·만료 세션 각 1 → DELETE 204, 그 course_id 의 auth_session 0행, 500 아님).
- `tests/integration/test_db_enroll.py` (new): `test_learner_email_unique_lower`(23505) · `test_enrollment_unique_per_course` · `test_enrollment_course_fk_blocks_delete`(23503) · `test_session_attachment_link_requires_url`(23514) · `test_enrollment_created_only_in_enter`(src 에서 `\binsert_enrollment\(` 호출은 enter.py 하나, `\bEnrollment\(` 생성은 crud/enrollment.py 하나, 정의 줄 제외).
- `tests/integration/test_db_concurrency.py` (new): `test_concurrent_enroll_capacity` · `test_concurrent_reissue_one_live` · `test_concurrent_reissue_then_enter_old_code_404`(A 재발급이 잠금을 쥔 동안 B 가 옛 코드로 새 등록 → A 커밋 뒤 B 404, enrollment 0) · 결정 (xiii) 기본이면 `test_concurrent_login_failures_serialized`. 이 파일 안 픽스처가 `migrated_db_url` 로 따로 엔진(NullPool)을 만들어 **커밋**하고, finally 에서 `Base.metadata.sorted_tables` 를 `TRUNCATE … RESTART IDENTITY CASCADE` 한다(r3 부록 D, 단일 연결 롤백으로는 행 잠금을 못 잰다). 순서를 기계로 고정한다: 세션 A 가 판정을 끝내고 커밋 전에 멈춘다 → B 를 태스크로 띄운다 → 제3 연결이 `pg_stat_activity.wait_event_type = 'Lock'` 을 보거나 B 가 끝날 때까지(최대 5초) 기다린다 → A 커밋 → B 결과 단언. 잠금이 없으면 B 가 먼저 끝나 시간에 기대지 않고 빨개진다.
- `tests/unit/test_enter_rules.py` (new): `test_enter_code_input_confusable_before_malformed` · `test_enter_code_input_normalizes_case_and_spaces` · `test_enter_card_state_needs_open_and_attachment`.
- `tests/fixtures/enter.py` (new) 〔정함〕: `enter_learner(client, code, email, name)` · `add_pdf(client, headers, session_id, data)` 도우미. 관리자 헤더는 T2a `tests/fixtures/courses.py::admin_headers`(:61)를 다시 쓴다.
- `tests/contracts/expected_paths.txt` (modify): 8줄을 더한다(22 → 30줄): `/v1/admin/attachments/{attachment_id}` · `/v1/admin/courses/{course_id}/enrollments` · `/v1/admin/courses/{course_id}/portal` · `/v1/admin/sessions/{session_id}/attachments` · `/v1/enter` · `/v1/enter/lookup` · `/v1/learner/courses/{course_id}/portal` · `/v1/learner/sessions/{session_id}/attachments`.

**문서**
- `docs/plans/T2b-enter-portal.md` (new, 뒤에 modify): 이 계획. 리뷰와 "계획과 다르게 한 것" 을 채운다.
- [`docs/process/plan.md`](../process/plan.md) (modify): T2b 행의 착수 조건에 "= 이 가지의 approve 커밋(충족)", 계획 파일 칸, 상태. T8 행 메모 한 줄: "Design 부록 A T8 행의 `test_concurrent_` 를 정확한 이름으로 좁힌다(T2b 가 같은 접두를 쓴다)". T5 행 메모 한 줄: "포털에 강사 이름을 넣으면 `test_no_personal_keys_portal` 의 `name` 키 검사와 키 이름을 맞춘다(시안 학습자.html:724)".
- [`docs/process/spec.md`](../process/spec.md) (modify): 2절 6·7·8행의 "예정: T2b …" → 실제 시험 경로 · 1절 plan.md 행 상태 · 3절 A2-3·A2-4 상태 칸.
- [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) (modify): 4절 0004 행(kind 5종 · description · file_id NO ACTION) · 4절 owner_kind 줄에 "T2b 등록됨" · 5절 6(잠금 대상 = course 행, 코드 행을 바꾸는 네 문 포함) · 11(삭제 경로가 첨부를 먼저 지움, 강의 삭제는 그 강의의 auth_session 행도 지움, 근거 칸 r3 부록 C) · 14(계약 ② 에 enroll) · 18(동시성 픽스처 방식 · 로그인 잠금 시험) · 20(`attachment_pdf_max_mb`). **부록 A T2b 동시성 행(159행)** 의 시험 이름 칸을 접두 `test_concurrent_` 에서 정확한 이름 `test_concurrent_enroll_capacity` · `test_concurrent_reissue_one_live` · `test_concurrent_reissue_then_enter_old_code_404`(+ (xiii) 기본이면 `test_concurrent_login_failures_serialized`)로 좁히고 규칙 칸에 "재발급 뒤 옛 코드 입장 404" 를 더한다(Design 136행 "그 T 의 계획이 이 표를 고쳐 바꿀 수 있다"). T8 행(175행)은 T8 이 고친다.
- [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) (modify, 결정 xiii): 바라는 결과 3(:34)의 개수를 고른 쪽으로 고친다. r3 §6 E-11 은 gitignore 파일이라 리드가 같은 값으로 고친다.
- `CLAUDE.md` (modify): Rules 경계 줄의 ② 설명에 enroll · 권한 쿼리 줄에 "등록된 owner_kind: session_attachment(T2b)".
- docs 목차(`okf index` 가 고친다).

바꾸지 않는 것: `alembic.ini`(사용자 미커밋 변경) · `.env` · `0001`~`0003` · T1·T2a 시험의 단언 · `tests/conftest.py` · `tests/contracts/conftest.py` · `tests/stale_patch_guard.py` · `tests/fixtures/courses.py` · `.claude/**` · `Makefile` · `.github/workflows/ci.yml` · 셸 스크립트 · templates · ADR · 미추적 `기획/`·`시안/`(읽기만).

## 작업 순서

커밋은 묶음마다 파일을 지정하고 메시지는 `-F` 파일로 넘긴다. `git add -A`·`git add .`·`git commit -a` 는 쓰지 않는다. 단계마다 관문이 녹색이어야 다음으로 간다.

1. 리드: T2a 구현이 끝나면 가지 `T2b-enter-portal` 을 T2a 머리에서 따고, 아래 대조로 T2a 이름을 다시 본다. 다르면 이 파일을 고친 뒤 `docs/plans/` 에 둔다. 대조 기대 출력은 `t2a-names-ok` 한 줄(이름 28개: 클래스 5 · 함수 22 · 상수 1) · `22` · `1` 이다(a762cb4 에서 확인). `okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크의 앞뒤 문장을 읽는다 → `okf index --apply` → `okf check --strict` → `위반 0건 — 통과`. 이 파일과 [`docs/index.md`](../index.md) · [`docs/plans/index.md`](index.md) 를 파일 지정해 `plan: T2b enter-portal` 로 커밋한다. 트레일러는 없다.

   ```bash
   for n in Course CourseDay Section CourseSession InviteCode; do git grep -qE "^class $n\(" HEAD -- src/classfit/models || echo "없음 $n"; done; for n in open_course issue_invite_code reissue_invite_code pause_invite_code resume_invite_code update_invite_code schedule_of remove_section remove_session course_status_at code_state_at course_scope get_course delete_course get_live_code update_code get_session_and_course list_sections list_sessions open_test_course admin_headers learner_headers; do git grep -qE "^(async )?def $n\(" HEAD -- src tests/fixtures || echo "없음 $n"; done; git grep -q '^INVITE_ALPHABET = ' HEAD -- src/classfit/service/rules/invite.py || echo "없음 INVITE_ALPHABET"; echo t2a-names-ok
   git show HEAD:tests/contracts/expected_paths.txt | wc -l | tr -d ' '                  # → 22
   git grep -c 'crud_course.delete_course(' HEAD -- src/classfit/app/endpoints/courses.py | cut -d: -f3   # → 1 (강의 DELETE 의 crud 직행 자리, 결정 ix)
   ```

2. T2a 병합 뒤 에이전트: `bash scripts/sync_task.sh`(`sync: T2b …`). 관문: `bash scripts/check_task_order.sh` → `task order: OK` · 작업 순서 1 의 대조 세 줄이 같은 출력. T2a 리뷰 수정으로 이름이 바뀌었으면 approve 전에 이 계획을 고친다.
3. 승인자: `approve: T2b` 빈 커밋. 이것이 python-multipart 승인이다. 결정 (i)~(xiv)(선택 항목 (xiii)·(xiv) 포함)를 바꾸려면 승인자가 approve 전에 말하고, 리드가 계획을 고친 뒤 approve 한다. 그 전에는 아래를 시작하지 않는다.
4. 의존성. 관문: `.venv/bin/python -c 'import python_multipart; print(python_multipart.__version__)'` 가 판을 찍는다 · `git diff requirements.txt | grep -E '^[-+][a-z]'` → `+python-multipart==<판>` 한 줄 · `git diff --stat requirements-dev.txt` 빈 출력. 커밋 `T2b: python-multipart 의존성`.
5. 설정 칸 → 0004 → models → crud → 통합 시험(`test_db_enroll.py`). 관문: `.venv/bin/alembic heads` → `0004 (head)` · `make migrate` 뒤 `.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/alembic check` → `No new upgrade operations detected.` · `.venv/bin/pytest -q` failed·error 0(T1·T2a 포함). alembic 1.20.0 은 식 색인을 반영한 식 글자로 비교한다. 그래서 모델에 같은 `Index(…, func.lower(email))` 를 두고 email 을 Text 로 둔다(`lower((email)::text)` 면 다르다고 본다). CHECK 는 비교하지 않으므로 통합 시험이 잰다. 커밋 `T2b: 0004 마이그레이션·모델·crud`.
6. rules → service/enroll → service/courses(portal · codes 잠금 · remove · sections 삭제 경로) → service/files/attachments → 계약 ② → 단위 시험. 관문: `.venv/bin/pytest tests/unit tests/integration -q` failed·error 0 · `make lint-imports` → `Contracts: 3 kept, 0 broken.` · `make gate` → `gate: OK`(300줄). 커밋 `T2b: service — 입장·포털·첨부·잠금, 계약 ② enroll`.
7. schemas → deps → endpoints(새 넷 + courses.py 강의 DELETE) → routers → expected_paths → 시험 도우미 → 계약 시험. 관문: `.venv/bin/pytest tests/contracts -q` failed·error 0 · E-10 줄 · 증명 표 1~13·18~22 녹색. 커밋 `T2b: 끝점·계약 시험`.
8. 동시성 시험. 관문: `.venv/bin/pytest tests/integration/test_db_concurrency.py -q` → (xiii) 기본 `4 passed`(대안 `3 passed`)를 세 번 연달아 · 뒤이어 `.venv/bin/pytest -q` 전체 녹색(정리 확인). 커밋 `T2b: 동시성 시험 — 정원·재발급·옛 코드·로그인 잠금`.
9. 문서(plan.md · spec.md · Design · intent · CLAUDE.md). okf 네 단계 → `위반 0건 — 통과`. 관문: `make okf` → `OKF guard OK`. 커밋 `T2b: 문서 — plan·spec·Design·intent·CLAUDE.md`.
10. `make verify`(파이프 없이) exit 0. 이어서 "증명" 의 명령 · 이웃 흐름 · 대조 실험 9개를 돌리고 기록 칸에 적는다.
11. 다른 세션의 reviewer 가 "리뷰" 절을 쓰고 Important 0 까지 고친다. DB 쓰기·권한·되돌리기 어려운 흐름이라 `verifier` 서브에이전트가 "증명" 을 다시 돌린다(CLAUDE.md 검증 표 · Design 5절 19).
12. `bash scripts/check_task_order.sh` → `task order: OK`. 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T2b-enter-portal`.

## 위험

| 위험 | 알아채는 법 | 완화 (출처) |
|---|---|---|
| T2a 이름·경로가 리뷰 중 바뀐다 | 작업 순서 1·2 의 대조 세 줄 · sync 충돌 | 대조가 다르면 approve 전에 고친다. approve 뒤 바뀌면 "계획과 다르게 한 것" 에 적는다 |
| 정원 경쟁: 동시 새 등록이 `max_seats` 를 넘는다 | `test_concurrent_enroll_capacity` · 대조 실험 1 | course 행 FOR UPDATE 뒤 세고 넣는다(결정 v, Design 5절 6) |
| 재발급 경쟁: 둘째 재발급이 23505 → 409 이거나 산 코드가 둘 | `test_concurrent_reissue_one_live` · 대조 실험 2 | 같은 course 행 잠금. 부분 유일 색인이 마지막 방어다(T2a) |
| 잠금을 기다린 입장이 같은 ORM 세션의 옛 코드 행으로 판정해 replaced·paused 코드로 새 등록이 된다 | `test_concurrent_reissue_then_enter_old_code_404` · 대조 실험 8 | 잠금 전에는 `course_id` 스칼라만, 잠금 뒤 `populate_existing=True` 로 다시 읽는다(결정 ii, orm/loading.py:1088-1094) |
| 로그인 잠금 키의 advisory lock 이 실제로 줄 세우는지 잰 적이 없다 | `test_concurrent_login_failures_serialized` · 대조 실험 7 | T1 nit 2 이관. 결정 (xiii) 대안이면 T8 로 넘어간다 |
| E-11 기대 개수가 intent:34·r3 §6 E-11 의 "3" 과 어긋난다 | 증명의 E-11 줄 | 결정 (xiii) 에서 고르고 문서 단계에서 intent 와 r3 를 같이 고친다 |
| 교차 강의 접근: B 수강생이 A 포털·첨부·파일을 연다 | `test_cross_course_portal_403` · 대조 실험 3 | 끝점의 course_id 대조 + crud 첫 WHERE `course_scope(subject)` + 파일 판정의 강의 대조(ADR-002 결정 1) |
| 이름 덮어쓰기: 다른 강의 등록이 이 강의 명단을 바꾼다 | `test_enrollment_name_isolated` · 대조 실험 4 | 이름·부서는 enrollment 만, learner 는 이메일만(r3 N9) |
| 이메일 대소문자·공백으로 같은 사람이 둘이 된다 | `test_p3_existing_email` · `test_learner_email_unique_lower` | 스키마 정규화 + `lower(email)` 유일 색인 + ON CONFLICT(결정 iv) |
| 혼동 문자가 일반 형식 오류로 묻힌다 | `test_p3_confusable` · `test_enter_code_input_confusable_before_malformed` | 혼동 문자를 먼저 본다. 알파벳 원본은 rules/invite.py 하나 |
| 업로드 크기·MIME 위조, 인증 전 대용량 스풀, 깨진 multipart 가 500 이 된다 | `test_admin_attachment_too_large_413` · `_without_length_411` · `_bad_multipart_400` · `_not_pdf_422` | FastAPI 는 폼 매개변수를 의존성보다 먼저 읽는다. 그래서 폼을 선언하지 않고 인증 뒤 Content-Length 를 보고 `async with request.form()` 으로 읽는다. 파싱 오류는 Starlette 의 400. 내용은 `%PDF-`, content_type 은 고정(결정 viii). nosniff·attachment 는 T1 files 끝점 |
| link 로 `javascript:` 같은 주소가 들어간다 | `test_admin_attachment_link_scheme_422` | http·https 만(결정 viii) |
| 응답에 맨 key 나 디스크 경로가 나간다 | `test_admin_attachment_pdf_upload_201` 의 href 모양 | `href` 는 T1 `href_for` 한 곳. 서명 URL 은 예약 칸 그대로(ADR-003 결정 2·3, r3 N12) |
| `session_attachment` 등록을 빠뜨려 모든 첨부가 404 | `test_admin_attachment_pdf_upload_201`(href GET 200) | 등록부는 scope.py 한 곳(Design 4절 순서) |
| 잠긴 세션의 파일이 href 로 열린다 | `test_portal_locked_attachments_403` · 대조 실험 5 | 파일 판정에 `is_open`(결정 x). 카드 판정은 rules, 파일 판정은 crud 라 두 곳이고 시험이 둘을 묶는다 |
| 포털에 개인정보가 나간다 | `test_no_personal_keys_portal` · `test_enter_lookup_hides_personal_fields` | 포털 스키마에 이름 칸이 없다(원칙 10, E-14). T5 가 강사 이름을 넣을 때 키 이름을 맞춘다(plan.md T5 메모) |
| stored_file 행이 고아로 남는다(첨부·세션·섹션·강의 삭제) | `test_admin_attachment_delete_removes_file_row` · `_owner_delete_removes_file_rows` · 대조 실험 6 | 삭제 경로 셋이 service 에서 먼저 지운다. 강의 DELETE 는 끝점 crud 직행을 `remove_course` 로 옮긴다. FK NO ACTION 이라 빠뜨리면 23503 으로 드러난다(결정 ix, r3 부록 C) |
| 잠금 순서가 경로마다 달라 교착(40P01 → 500)이 난다 | 리뷰 · 동시성 시험 | 모든 쓰기 경로는 course 행 → invite_code → learner·enrollment·auth_session 순서로 잠근다(입장 · 코드 관리 네 문 · `remove_course`, 결정 v). 이 순서를 뒤집는 새 경로를 만들지 않는다. 경합은 같은 강의의 입장·코드 관리·강의 삭제 사이로 한정되고 트랜잭션이 짧다 |
| 입장이 강의 행을 잠근 채 등록하는 사이 강의 DELETE 가 enrollment 0 을 믿고 지워 23503 → 500 이 된다 | 리뷰 | `remove_course` 맨 앞의 `lock_course`(결정 v·xi). 입장 쪽은 `lock_course` 가 None 이면 404(결정 ii) |
| 수강생 없는 강의 DELETE 가 남은 learner 세션 행 때문에 23503 → 500 이다(T2a reviewer nit 3) | `test_courses_delete_clears_course_sessions` · 대조 실험 9 | `remove_course` 가 같은 트랜잭션에서 그 강의의 auth_session 행을 먼저 지운다(결정 xi, 0003 FK NO ACTION) |
| pdf 첨부 행에 file_id 가 빈 채 커밋된다(CHECK 로 못 막음) | `test_admin_attachment_pdf_upload_201` | 넣기는 `add_pdf_attachment` 한 함수. id 가 Identity always 라 첨부 id 를 미리 못 받는다(결정 ix) |
| 종료·만료 경계가 T2a 와 갈린다 | `test_p3_ended` · `test_p3_expired` | 판정은 T2a rules 의 `code_state_at`·`course_status_at` 만 쓴다. 종료일 다음 날부터 ended, 만료일 당일까지 유효(T2a 결정 iii) |
| 종료·보관 강의 기존 수강생이 막힌다 | `test_p3_ended` · `test_portal_ended_course_existing_learner_200` | 재입장은 상태 판정 앞(결정 ii, ADR-002 결정 4). 보관은 판정에 쓰지 않는다(결정 vii) |
| 0004 가드가 dev 를 멈추거나 FK 잠금이 길다 | 가드 메시지 · `lock_timeout` | T2a 정리 줄로 learner 세션 행을 지운다. 표 생성은 새 표라 기존 행 검사가 없다 |
| python-multipart 없이 폼을 읽으면 Starlette 가 AssertionError(500)를 낸다 | 작업 순서 4 관문 · 첨부 계약 시험 | approve 전에는 의존성·코드 모두 손대지 않는다. 설치가 안 되면 멈추고 보고한다 |
| E-10 개수가 13 이 아니다(다른 시험이 접두를 쓰거나 parametrize) | 증명의 E-10 줄 | 네 접두는 13건에만 쓴다 |
| 동시성 시험이 남긴 커밋 행이 다른 시험을 깬다 | 작업 순서 8 의 전체 재실행 | finally TRUNCATE, 세션마다 base 부터. 실패해도 다음 실행이 복구된다(r3 부록 D) |
| 무차별 대입으로 산 코드를 찾는다 | — | 결정 (xiv). 기본은 32^6 · 재발급 · 요청 제한 2차, 대안은 T1 `auth_attempt` 재사용 429(r3 부록 F) |
| Design 부록 A 의 `test_concurrent_` 가 T2b·T8 두 행이라 T8 행 검사가 T2b 시험으로 통과한다(check_docs.sh:201-205) | 리뷰 | T2b 행을 정확한 이름으로 좁히고, plan.md T8 행에 같은 일을 메모한다(문서 절) |
| 끝점 500줄 · service·crud 300줄을 넘는다 | `make gate`(check_file_size) | 끝점 넷 · service 넷으로 나눴다. 넘으면 나누고 "계획과 다르게 한 것" 에 적는다 |
| iCloud dataless venv 가 EDEADLK 를 낸다 | `Resource deadlock avoided` | 재시도, verifier 는 스크래치 venv(T0a 전례) |

## 증명

r3 §6 의 T2b 몫과 plan.md 증명 요약이다. E-8·E-11·E-13·E-14 는 T2b 시점 값이다.

```bash
bash scripts/check_task_order.sh                    # E-1 T2a 병합 + sync 뒤 → "task order: OK"
make verify                                         # E-3 exit 0 · "gate: OK" · "All checks passed!" · "Contracts: 3 kept, 0 broken." · "passed"(failed·error·skipped 0) · 끝 줄 "OKF guard OK"
.venv/bin/alembic heads                             # E-8 → "0004 (head)"
.venv/bin/pytest tests/contracts/test_api_openapi.py -q                 # E-13 → "1 passed"(expected_paths 30줄)
test "$(.venv/bin/pytest tests/contracts/test_api_enter.py --co -q | grep -cE '::test_(p3|reissue|cross_course|enrollment_name)_')" -eq 13 && .venv/bin/pytest tests/contracts/test_api_enter.py -q   # E-10 → "18 passed"
.venv/bin/pytest tests/integration/test_db_concurrency.py -q            # E-11 T2b 시점 → (xiii) 기본 "4 passed" · 대안 "3 passed"
test "$(.venv/bin/pytest tests -q --co -k no_personal_keys | grep -c '::test_no_personal_keys_')" -ge 1 && .venv/bin/pytest tests -q -k no_personal_keys   # E-14 T2b 몫 → "1 passed"
git diff master...HEAD -- requirements.txt | grep -E '^[-+][a-z]'      # → "+python-multipart==<판>" 한 줄
for n in test_p3_active test_p3_preparing test_p3_ended test_p3_expired test_p3_paused test_p3_full test_p3_not_found test_p3_existing_email test_p3_confusable test_reissue_old_code_not_found test_reissue_keeps_sessions test_cross_course_portal_403 test_enrollment_name_isolated test_no_personal_keys_portal test_concurrent_enroll_capacity test_concurrent_reissue_one_live test_concurrent_reissue_then_enter_old_code_404; do grep -rqE "def ${n}\(" tests || echo "없음 $n"; done; grep -rqE "def test_portal_locked_[A-Za-z0-9_]*\(" tests || echo "없음 test_portal_locked_"; echo table-ok   # 병합 전 check_docs ④ 근사(좁힌 Design 행 기준) → "table-ok" 한 줄만
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh                  # 병합 뒤 ④ 대상에 T2b 7행 → "docs check: OK"
```

| # | 관문 (plan.md T2b 행 · r3 부록 B T2b) | 명령 `.venv/bin/pytest <노드> -q` | 기대 (`1 passed` 와 함께) |
|---|---|---|---|
| 1 | P3 활성 | `tests/contracts/test_api_enter.py::test_p3_active` | 201 · bearer · expires_at 이 약 1일 뒤 · learner 1(소문자 이메일) · enrollment 1 · 그 토큰으로 포털 200 |
| 2 | P3 준비 중 | `…::test_p3_preparing` | lookup 200 `state=preparing` + notice "시작일 <start_on>" · enter 201 + 같은 notice |
| 3 | P3 종료 | `…::test_p3_ended` | 새 이메일 409 `/problems/course-ended`, enrollment 수 그대로 · 기존 수강생 200 `reentered` |
| 4 | P3 만료 | `…::test_p3_expired` | expires_on 어제 → 409 `/problems/invite-code-expired` · 기존 200 |
| 5 | P3 정지 | `…::test_p3_paused` | `:pause` 뒤 409 `/problems/invite-code-paused` · 기존 200 |
| 6 | P3 정원 | `…::test_p3_full` | max_seats 1 → 둘째 409 `/problems/course-full` · 첫째 재입장 200 |
| 7 | P3 없는 코드 | `…::test_p3_not_found` | lookup·enter 404 `/problems/invite-code-not-found` |
| 8 | P3 이미 등록 | `…::test_p3_existing_email` | 대소문자 다른 이메일 200 `reentered` · name 은 처음 값 · enrollment 1 · auth_session 2 |
| 9 | P3 혼동 문자 | `…::test_p3_confusable` | `AB0CDE`·`abcdo1` → lookup·enter 422 `/problems/invite-code-confusable` |
| 10 | 재발급 옛 코드 | `…::test_reissue_old_code_not_found` | 옛 코드 응답 = 없는 코드 응답(상태 · instance 뺀 본문) |
| 11 | 재발급 세션 유지 | `…::test_reissue_keeps_sessions` | 옛 토큰 포털 200 · 새 코드 + 이메일 200 |
| 12 | 교차 강의 403 | `…::test_cross_course_portal_403` | B 수강생 → A 포털 · A 세션 첨부 목록 · A 파일 href 모두 403 |
| 13 | 이름 분리 | `…::test_enrollment_name_isolated` | A 에 "김가명", 같은 이메일로 B 에 "이가명" → A 명단 "김가명" · learner 1 |
| 14 | 정원 동시성 | `tests/integration/test_db_concurrency.py::test_concurrent_enroll_capacity` | B 가 잠금에서 기다린 뒤 full · enrollment 1 |
| 15 | 재발급 동시성 | `…::test_concurrent_reissue_one_live` | 둘 다 성공 · 산 행 1 · replaced 2 |
| 16 | 재발급 뒤 옛 코드 입장 | `…::test_concurrent_reissue_then_enter_old_code_404` | B 가 잠금을 기다린 뒤 404 `/problems/invite-code-not-found` · enrollment 0 |
| 17 | 로그인 잠금 동시성(T1 이관, (xiii) 기본) | `…::test_concurrent_login_failures_serialized` | 실패 9 커밋 뒤 A 10번째, B 는 `locked` |
| 18 | 포털 개인 키 없음 | `tests/contracts/test_api_portal.py::test_no_personal_keys_portal` | 키 0 |
| 19 | 준비 중 카드 | `tests/contracts/test_api_portal.py -k test_portal_locked_` | `3 passed` |
| 20 | 첨부 삭제가 파일 행도 지움 | `tests/contracts/test_api_attachments.py::test_admin_attachment_delete_removes_file_row` | 204 · stored_file 0 · 옛 href 404 · audit 2(`session_attachment`·첨부 id) |
| 21 | 수강생 있는 강의 DELETE | `tests/contracts/test_api_enrollments.py::test_courses_delete_with_enrollments_409` | 409 `/problems/conflict` · 행 그대로 |
| 22 | 수강생 없는 강의 DELETE 의 세션 행 | `tests/contracts/test_api_enrollments.py::test_courses_delete_clears_course_sessions` | 204 · 그 course_id 의 auth_session 0행 · course 0행 |

**이웃 흐름 — 실제 호출**(CLAUDE.md "바뀐 동작 1개와 이웃 흐름 2개"). dev DB 에서 `make migrate` 뒤, 다른 터미널에서 `CLASSFIT_FILE_STORE_ROOT=var.nosync/files make run`(셸 환경이 `.env` 보다 앞, core/config.py:6)으로 띄운다. 날짜는 macOS `date -v` 다. `is_open` PATCH 는 T2a `SessionPatchIn`(schemas/course.py:312)이 받는다. 마지막 정리 줄이 남긴 dev 행을 한 트랜잭션으로 지운다.

```bash
.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/python -m scripts.create_admin --login-id admin-t2b --apply   # 비밀번호는 getpass 두 번
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/admin/login -H 'content-type: application/json' -d '{"login_id":"admin-t2b","password":"<입력한 값>"}' | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
H="Authorization: Bearer $TOKEN"; S=$(date +%F); E=$(date -v+30d +%F); tmp=$(mktemp -d); printf '%%PDF-1.4\n%%%%EOF\n' > "$tmp/a.pdf"
read CID CODE <<<"$(curl -s -X POST localhost:8000/v1/admin/courses -H "$H" -H 'content-type: application/json' -d "{\"start\":\"blank\",\"title\":\"AI 활용 기초\",\"client_name\":\"A사\",\"method\":\"집체\",\"hours_per_person\":16,\"start_on\":\"$S\",\"end_on\":\"$E\",\"day_count\":0,\"day_start\":\"13:00\",\"day_end\":\"17:00\"}" | .venv/bin/python -c 'import json,sys; b=json.load(sys.stdin); print(b["course"]["id"], b["invite_code"]["code"])')"
SEC=$(curl -s -X POST "localhost:8000/v1/admin/courses/${CID}/sections" -H "$H" -H 'content-type: application/json' -d '{"title":"공통"}' | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
SID=$(curl -s -X POST "localhost:8000/v1/admin/courses/${CID}/sections/${SEC}/sessions" -H "$H" -H 'content-type: application/json' -d '{"title":"생성형 AI 개요"}' | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])'); curl -s -o /dev/null -w '%{http_code}\n' -X PATCH "localhost:8000/v1/admin/sessions/${SID}" -H "$H" -H 'content-type: application/json' -d '{"is_open":true}'   # 200
AID=$(curl -s -X POST "localhost:8000/v1/admin/sessions/${SID}/attachments" -H "$H" -F kind=pdf -F title=1교시 -F "file=@$tmp/a.pdf;type=application/pdf" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')   # 201
LTOKEN=$(curl -s -X POST localhost:8000/v1/enter -H 'content-type: application/json' -d "{\"code\":\"$CODE\",\"email\":\"Learner-A@example.com\",\"name\":\"김가명\"}" | .venv/bin/python -c 'import json,sys; b=json.load(sys.stdin); print(b["reentered"], b["name"], file=sys.stderr); print(b["access_token"])')   # 바뀐 동작 → stderr "False 김가명"
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/v1/enter -H 'content-type: application/json' -d "{\"code\":\"$(echo $CODE | tr A-Z a-z)\",\"email\":\"learner-a@example.com\",\"name\":\"다른이름\"}"   # 200(재입장)
HREF=$(curl -s "localhost:8000/v1/learner/courses/${CID}/portal" -H "Authorization: Bearer $LTOKEN" | .venv/bin/python -c 'import json,sys; s=json.load(sys.stdin)["sections"][0]["sessions"][0]; print(s["state"], file=sys.stderr); print(s["attachments"][0]["href"])'); curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000${HREF}" -H "Authorization: Bearer $LTOKEN"   # stderr "open" · 200
CID2=$(curl -s -X POST localhost:8000/v1/admin/courses -H "$H" -H 'content-type: application/json' -d "{\"start\":\"blank\",\"title\":\"데이터 기초\",\"client_name\":\"B사\",\"method\":\"집체\",\"hours_per_person\":8,\"start_on\":\"$S\",\"end_on\":\"$E\",\"day_count\":0,\"day_start\":\"13:00\",\"day_end\":\"17:00\"}" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["course"]["id"])'); curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000/v1/learner/courses/${CID2}/portal" -H "Authorization: Bearer $LTOKEN"   # 403
curl -s -X POST localhost:8000/v1/enter -H 'content-type: application/json' -d '{"code":"AB0CDE","email":"learner-b@example.com","name":"이가명"}'   # 422 → type "/problems/invite-code-confusable"
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "localhost:8000/v1/admin/courses/${CID}" -H "$H"; curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "localhost:8000/v1/admin/attachments/${AID}" -H "$H"; curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000${HREF}" -H "$H"   # 409 · 204 · 404
/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -v ON_ERROR_STOP=1 -c "delete from audit_log where (target_type = 'course' and target_id in ('$CID', '$CID2')) or (target_type = 'session_attachment' and target_id = '$AID') or (action = 'admin.create' and target_type = 'admin_account' and target_id in (select id::text from admin_account where login_id = 'admin-t2b')); delete from auth_session where course_id in ($CID, $CID2) or (principal_type = 'admin' and principal_id in (select id from admin_account where login_id = 'admin-t2b')); delete from enrollment where course_id in ($CID, $CID2); delete from learner where lower(email) = 'learner-a@example.com'; delete from course where id in ($CID, $CID2); delete from auth_attempt where kind = 'admin_login' and subject_hash = encode(sha256('admin-t2b'::bytea), 'hex'); delete from admin_account where login_id = 'admin-t2b'"   # 정리. 첨부는 위 DELETE 가 지웠고 나머지는 CASCADE
SHA=$(shasum -a 256 "$tmp/a.pdf" | cut -d' ' -f1); rm -f "var.nosync/files/${SHA:0:2}/$SHA"; rm -rf "$tmp"; pkill -f 'uvicorn classfit.main:app' ; /usr/sbin/lsof -nP -iTCP:8000 -sTCP:LISTEN || echo port-free   # → "port-free"
```

**대조 실험**(커밋 뒤 임시 clone 에서만, CLAUDE.md). 실험마다 `tmp=$(mktemp -d)` 뒤 `git clone -q --no-hardlinks . "$tmp/cN"` 사본을 따로 만든다. 사본을 고치고, 원본 `.venv` 와 `PYTHONPATH="$tmp/cN/src"` 로 그 시험만 `--rootdir "$tmp/cN"` 으로 돌려 빨간지 본다. 사본에는 `.env` 가 없으니 `CLASSFIT_TEST_DATABASE_URL` 을 셸 환경 변수로 넘긴다(tests/conftest.py:36).
1. `enter_course` 의 `lock_course` 호출을 뺀다: `test_concurrent_enroll_capacity` 가 빨개진다(enrollment 2).
2. `reissue_invite_code` 의 `lock_course` 를 뺀다: `test_concurrent_reissue_one_live` 가 빨개진다(B 409).
3. 수강생 포털 끝점의 course_id 대조와 `course_scope` learner 갈래를 `true()` 로: `test_cross_course_portal_403` 이 빨개진다(200).
4. 기존 learner 의 새 등록 때 그 learner 의 모든 enrollment.name 을 새 이름으로 UPDATE 한다: `test_enrollment_name_isolated` 가 빨개진다.
5. `session_attachment` 파일 판정에서 `is_open` 조건을 뺀다: `test_portal_locked_attachments_403` 이 빨개진다(href 200).
6. `delete_attachment` 에서 stored_file 행 삭제를 뺀다: `test_admin_attachment_delete_removes_file_row` 가 빨개진다.
7. (xiii) 기본일 때 `admin_login` 의 `lock_attempt_key` 호출을 뺀다: `test_concurrent_login_failures_serialized` 가 빨개진다(B `failed`).
8. `enter_course` 가 잠금 전에 코드 ORM 행을 읽고 잠금 뒤 `populate_existing` 없이 다시 읽게 한다: `test_concurrent_reissue_then_enter_old_code_404` 가 빨개진다(201).
9. `remove_course` 의 `delete_course_sessions` 호출을 뺀다: `test_courses_delete_clears_course_sessions` 가 빨개진다(23503 → 500).

정리: `rm -rf "$tmp"` 뒤 `git status --short` 가 실험 전과 같다. 동시성 실험이 남긴 커밋 행은 다음 실행이 base 부터 지운다.

| 기록 칸 | 값 |
|---|---|
| 착수 조건 결정 (i)~(xiv) 변경 여부 · (xiii)·(xiv) 선택 (approve 커밋 해시 · python-multipart 승인 겸함) | 변경 없음. (xiii) 기본(로그인 잠금 시험 포함, E-11 4 passed) · (xiv) 기본. approve `f636ce9`(python-multipart 승인 겸함). r3 §6 E-11 기대값은 리드가 "5 passed"(T2b 시점 4 · T8 뒤 5)로 고침(gitignore) |
| T2a 최종 이름 대조 세 줄 출력 · sync 커밋 해시 · `check_task_order` 출력 | `t2a-names-ok` · `22` · `1`(f047294·f3fcabc 시점, a762cb4 와 같음) · sync `f3fcabc`(master c46660e → 가지) · `task order: OK`(master..가지 3개 → 계획 갱신 포함 11개) |
| `requirements.txt` diff 행 · python-multipart 판 | `+python-multipart==0.0.32` 한 줄(`make lock`), `requirements-dev.txt` 변경 0, `import python_multipart` → `0.0.32`. 커밋 `dbb8706` |
| `make verify` 끝 20줄 | HEAD `0118897` exit 0(파이프 없이, 로그 파일): `gate: OK` · `All checks passed!` · `Contracts: 3 kept, 0 broken.` · 시험 파일 목록 끝 `tests/unit/test_status_rules.py ..... [100%]` · `============================= 178 passed in 7.19s ==============================` · `OKF_PYTHON=.venv/bin/python bash scripts/okf/guard.sh docs` · `OKF guard OK`. T2a 121 → 178 passed(failed·error·skipped 0). 리뷰 반영 `5a1a3ed` 뒤 재실행 exit 0 `179 passed in 7.45s`(로그 t2b-wrap/verify-after-nits.log) |
| `alembic heads` · dev `alembic check` | `0004 (head)` · dev `make migrate` → `Running upgrade 0003 -> 0004`(learner 세션 행 0, 정리 불필요) · dev `alembic check` → `No new upgrade operations detected.` · 0004 가드 실측(classfit_test: 0003 + 수강생 세션 1행 → "0004 중단 - learner 표가 없던 때의 수강생 auth_session 행 1 개", 지운 뒤 통과, downgrade 0003 왕복 통과) |
| E-10 수집 수 · E-11 · E-13 · E-14 출력 | E-10 `count=13` → `18 passed` · E-11 `4 passed`(worker-a 세 번 연달아 1.48s·1.20s·1.23s, 리드 1.23s) · E-13 `1 passed`(expected_paths 30줄) · E-14 `count=1` → `1 passed, 177 deselected` |
| 증명 표 22항목 출력 | 1~18·20~22 각 `1 passed`, 19 `3 passed, 4 deselected`(리드, classfit_c_test; worker-b 도 1~13·18~22 노드별 exit 0) |
| 이웃 흐름 응답(200 · 201 · stderr 줄 · 200 · open · 200 · 403 · 422 · 409 · 204 · 404) · `port-free` | worker-c(dev, make run 백그라운드, create_admin 은 expect): 로그인 200 · 강의 201 · 섹션·세션 201 · PATCH 200 · 첨부 201 · **입장 201 stderr `False 김가명`**(expires_at 24h 뒤) · 소문자 코드 재입장 200(name 김가명 유지) · 포털 stderr `open` + href 200(바이트 동일) · 다른 강의 포털 403 `/problems/forbidden` · 혼동 문자 422 `/problems/invite-code-confusable` · 강의 DELETE 409 `/problems/conflict` · 첨부 DELETE 204 · 옛 href 404 · 정리 psql exit 0 · `port-free`. uvicorn 500·Traceback 0, 정리 뒤 dev 행 전부 0 |
| 대조 실험 9개(빨개진 시험 이름 · 단언) · 정리 뒤 `git status --short` | 9/9 빨강(임시 clone, classfit_b_test, 대조군 9 passed): 1 `test_concurrent_enroll_capacity` `('created', False) == ('full', True)` · 2 `test_concurrent_reissue_one_live` B 23505 → Conflict 409 · 3 `test_cross_course_portal_403` `200 == 403` · 4 `test_enrollment_name_isolated` A 명단 `'이가명' != '김가명'` · 5 `test_portal_locked_attachments_403` href `200 == 403` · 6 `test_admin_attachment_delete_removes_file_row` StoredFile `1 == 0` · 7 `test_concurrent_login_failures_serialized` `('failed', False) == ('locked', True)` · 8 `test_concurrent_reissue_then_enter_old_code_404` `('created', True) == ('not_found', True)` · 9 `test_courses_delete_clears_course_sessions` `ForeignKeyViolation fk_auth_session_course_id_course`(23503, 계약 client 는 raise_app_exceptions 라 예외로 드러남). 정리 뒤 `git status --short` 실험 전과 같음(미추적 4개) |
| verifier 세션 · 날짜 · 판정 | verifier-t2b(에이전트 세션, 저장소 무변경) · 2026-10-22 · **PASS — 증명 충족**: check_task_order OK(9개) · `make verify` exit 0(`178 passed in 8.03s`, OKF guard OK) · 증명 블록(E-8·E-10 13→18·E-11 4 passed ×6·E-13 30줄·E-14·requirements 한 줄·table-ok·check_docs ④ 13행) · 표 22 노드별 passed + 시험 본문 단언 대조(전부 표와 같거나 강함; 16 은 service outcome `not_found` 단언, HTTP 404 는 7·10 이 덮음) · 이웃 흐름 재실행(201·200·201·`False 김가명`·`open`·200·403·422·409·204·404·`port-free`; 소문자 재입장 200 reentered=True 는 래퍼 인용 문제를 고친 2차 실행으로 확인) · 대조 실험 1·5·9 재측정 전부 빨강 · 평문 0(IP 리터럴은 192.0.2.10 뿐). 발견: 기록·리뷰·편차 칸 비어 있음(이 커밋으로 채움) · ④ 는 병합 뒤 재실행 |
| 병합 뒤 `check_docs.sh` ④ 대상 행 수 | `④ 병합된 T: T0a T0b T1 T2a T2b · 대응표 42행 중 대상 20행 · docs check: OK`(T3 문서 커밋에서 기록), master push cb5edaa CI run 39733979529 success |

## 리뷰

reviewer-t2b(다른 세션) · 2026-10-22 · 범위 `git diff master...HEAD`(c46660e → 0118897, 57파일, 커밋 f047294 … 0118897). 패스 Bugs → Security → Compliance. **Important 0건 · Nit 5건**(개수만 적은 nit 2건은 아래 보류). 시험 실행은 verifier 몫이라 돌리지 않았다.

확인한 것(근거): 결정 (ii) 판정 순서 그대로(`service/rules/invite.py:17-26` → `crud/invite_code.py:24-31` → `crud/course.py:31-44` → `service/enroll/enter.py:159-168` → 재입장 :172-182 → 상태 → 정원 :106-110 → 이름 → 새 등록만 learner·enrollment :192-196) · (v) 네 문 맨 앞 `_lock`(`service/courses/codes.py:108-113, 118, 131, 146, 160`) · `remove_course` 순서(`service/courses/remove.py:22-29`) · 섹션·세션 삭제 앞 첨부 정리(`sections.py:49-52, 90-93`) · 교착 순서를 뒤집는 쓰기 경로 없음 · (viii) 인증 뒤 본문 읽기와 404 → 411/413 → form → 422 → 501 → 413 → `%PDF-` 422 → 201(`app/endpoints/attachments.py:195-243`), content_type 고정(`service/files/attachments.py:28, 84`), http·https 만(`schemas/attachment.py:40-49`), audit 2종(`service/files/attachments.py:88-95, 136-143`) · (ix)·(x) 첨부 행 → stored_file → `set_file_id`(`service/files/attachments.py:76-87`), 지우기 순서(`crud/attachment.py:117-134`), learner 갈래·`OWNER_KINDS["session_attachment"]`(`crud/scope.py:40-69`), 목록 첫 WHERE(`crud/attachment.py:75-83`, `crud/enrollment.py:57-65`) · (vi)·(vii) `LearnerCaller`(`app/deps.py:77-83`), 포털 course_id 대조 403(`app/endpoints/portal.py:80-82`), 잠긴 카드 제외(`:33-45`, `service/courses/portal.py:95`), 개인 칸 없음 · 0004 가드·역순·식 색인 글자 일치(`alembic/versions/0004_enter_portal.py:52-64, 130-137`, `models/learner.py:38`) · 동시성 시험 순서 고정·`waited is True`·TRUNCATE(`tests/integration/test_db_concurrency.py:44-57, 65-116`) · Compliance: 바뀐 파일이 계획과 일치(추가분은 편차 목록), T1·T2a 시험·conftest·fixtures/courses 변경 0, skip·완화 없음, `table-ok`, E-10 접두 13·다른 파일 0, 시험 수 18·7·10·4·4, expected_paths 30, requirements 증가 1행, 계약 ②, 증명 표 1~22 기대 = 단언, (xiv) 기본.

- **Nit 1 · Bugs · `src/classfit/schemas/attachment.py:52-57, 72-74`** — `description` 은 `_blank_is_none` 이 NUL 만 거르고 제어 문자는 통과시킨다. `title`(:60-64)·입장 스키마 세 칸(`schemas/enter.py:43-50`)과 정책이 갈린다. → **반영** `5a1a3ed`: `no_control_chars` 뒤 strip-or-None, 시험 추가.
- **Nit 2 · Bugs · `service/files/attachments.py:59-96` · `service/courses/sections.py:49-52, 90-93` · `service/courses/remove.py:22-29`** — 첨부 넣기는 강의 행을 잠그지 않는다. 관리자 둘이 같은 세션에 넣기와 세션·섹션·강의 삭제를 동시에 하면 삭제 쪽이 미커밋 첨부를 못 보고 23503 → 500(손상·유출 없음, 재시도 204). 계획 위험 표가 경합 범위를 입장·코드 관리·강의 삭제로 한정해 위반은 아님. → **문서**: 편차 23 + plan.md T6 행 메모("첨부 쓰기 경로는 course 잠금 밖, T6 이 넣기·지우기도 `lock_course` 로 들일지 정한다").
- **Nit 3 · Compliance · `docs/plans/T0b-sdlc-okf.md:199` · `docs/plans/T2a-open-course.md:228`** — 이전 계획의 기록 칸(CI · 병합 뒤 ④)을 이 가지가 채웠고 계획 "바뀌는 파일" 에 없다. 사실 기록이라 되돌릴 일은 아님. → **문서**: 편차 12 에 명시.
- **Nit 4 · 스타일 · `src/classfit/service/courses/codes.py:139-150`** — `resume_invite_code` 가 `course` 객체를 받지만 `_lock(session, course.id)` 로 다시 읽어 id 로만 쓴다. → **반영** `5a1a3ed`: `course_id` 로 서명 통일, 끝점이 `course.id` 를 넘김.
- **Nit 5 · Compliance · `src/classfit/schemas/enter.py:53`** — `Code` 가 `max_length=64` 라 65자 초과가 `/problems/invite-code-malformed` 가 아니라 일반 422. 결정 (i) 은 길이 오류를 malformed 로 둔다. → **반영** `5a1a3ed`: `parse_invite_input` 이 길이 초과를 malformed 로, Field 상한은 더 크게. 시험 보강.
- **보류(개수만 적은 nit 2, 승인자 판단)**: 413 안내문이 PDF 상한이 아니라 본문 상한(51MiB)을 찍음(`app/endpoints/attachments.py:105`) · lookup 의 `_failure(request, "ok")` 방어 분기가 KeyError 경로를 품음(`app/endpoints/enter.py:90-96`).

의견: 코드는 결정 (i)~(xiv)·위험 표 완화·CLAUDE.md Rules 와 맞고 시험 약화 없음. 기록 칸·`make verify` 출력·verifier 판정이 채워지면 병합 가능(결정은 승인자).

## 계획과 다르게 한 것

리드 · worker-a · worker-b · 리뷰 반영 순. 번호는 기록용이다.

**리드**
1. 워커 2명 분할(계획 "레인 A, 워커 하나"). 리드가 작업 순서 2·4·10 을 맡았다(위 실행 소유).
2. worker-b 전용 시험 DB `classfit_c_test` 를 새로 만들었다. 세 DB 를 동시에 썼다(a `classfit_test` · b `classfit_c_test` · 리드·verifier·대조 실험 `classfit_b_test`).
3. r3 §6 E-11 기대값을 "5 passed"(T2b 시점 4 · T8 뒤 5)로 고쳤다(gitignore 파일, 결정 xiii 기본).
4. 사용자의 T2b approve 커밋이 처음엔 이 저장소에 없었다("커밋완료" 뒤 확인: 가지 머리 f047294, 모든 ref 에 없음). 재실행 요청 뒤 `f636ce9` 로 들어왔다. 코드 변경은 그 뒤에만 시작했다.
5. 증명 표 22 는 리드가 `classfit_c_test` 에서 돌렸다(계획은 DB 를 정하지 않음). `make verify` 는 `.env` 기본이다.
6. 증명 표 16 의 기대 "404 `/problems/invite-code-not-found`" 는 동시성 시험에서 service outcome `not_found` 로 단언한다(워커 11). 404 type 매핑은 표 7·10 의 끝점 시험이 잰다(verifier 확인).

**worker-a**
6. `tests/integration/test_db_enroll.py` 에 계획 5건 외 crud 도우미 시험 6건을 더했다(`test_learner_get_or_create_reuses_row` · `test_session_attachment_owner_check_scope` · `test_session_attachment_lists_scope` · `test_session_attachment_delete_under_scopes` · `test_course_sessions_delete_only_that_course` · `test_enrollment_list_scope_and_email`, 예약 접두 없음) → 11 passed.
7. `test_enrollment_created_only_in_enter` 는 5단계(2a90c24)엔 "호출 ⊆ {enter.py}" 로 두고 8단계(ddee125)에서 계획 문구대로 `== ["service/enroll/enter.py"]` 로 좁혔다(B 의 enter.py 가 없던 시점의 녹색 유지).
8. 관리자 명단 이메일은 `Enrollment.learner` 관계(lazy="raise") + `list_stmt` 의 joinedload 로 읽는다(계획 미정).
9. 첨부 삭제는 stored_file 행을 file_id 가 아니라 소유 키(owner_kind·owner_id)로 지운다. `get_attachment` · 형 별칭 `AttachmentRow` 를 더했다.
10. 계획에 이름이 없던 색인은 `ix_session_attachment_session_id_sort_id`.
11. 동시성 시험은 서비스 단(enter_course · reissue_invite_code · admin_login)을 부른다(끝점 미의존). 그래서 증명 16 은 HTTP 404 가 아니라 outcome `not_found` 를 단언하고 404 매핑은 계약 시험 몫이다. 네 시험 모두 "B 가 잠금을 기다렸다"(waited True)를 함께 단언한다. B 쪽 안전판 `SET LOCAL lock_timeout = '10s'`.
12. 문서(리드 승인 4건): plan.md T2a 행을 "완료. master `c46660e`" 로 · T2b 행 증명 요약을 "동시성 4" 로 · T5·T8 메모를 착수 조건 칸에 "없음. 메모: …" 로 · Design 5절 6·11·18 과 부록 A T2b 행 근거 칸에 결정 번호. 추가로 미뤄 둔 기록 둘: T0b 계획 기록 칸 CI 줄(run 39708822144) · T2a 계획 기록 칸 "병합 뒤 check_docs ④"(42행 중 13행). T1·T2a 계획엔 CI 칸이 없어 만들지 않았다.

**worker-b**
13. replaced 코드는 재입장 판정보다 앞에서 not_found 다(결정 i · 증명 10·16 의 해석, 리드 확인).
14. 수강생 첨부 목록의 "잠김" 은 `card_state`(is_open ∧ 첨부 ≥ 1)로 잰다. 세션 행은 `get_session_and_course` 로 먼저 찾아 없으면 404, 있는데 잠겼거나 남의 강의(scope 로 첨부 0행)면 403 — 범위 판정을 service 에 복제하지 않았다.
15. `build_portal` 은 today 를 받지 않는다. 강의 status·notice 는 끝점이 `course_status_of`(같은 courses 구성요소)와 `Today` 로 계산한다.
16. `service/files/attachments.py` 는 크기·모양 거절을 `PdfRejected` 예외로 내고 끝점이 413·422 로 바꾼다. `app/errors.py` 는 바꾸지 않았다.
17. 수강생 첨부 목록 응답은 Design 5절 2 의 `Page{items, next_cursor, has_more}` 다(계획에 모양 없음). 한 쪽에 다 주어 has_more 는 늘 거짓.
18. `tests/fixtures/enter.py` 에 계획의 `enter_learner`·`add_pdf` 외에 `add_section`·`add_session`·`json_keys`·`PERSONAL_KEYS`·`bearer` 를 더했다.
19. `EnterIn` 의 name·dept 는 빈 문자열을 안 준 것으로 본다. 재입장 때 빈 이름을 보내도 422 가 아니고, 새 등록에 이름이 없을 때만 service 가 422(`body.name`)를 낸다.
20. 첨부 POST 는 kind=pdf 에 url 을 주면 422 다(DB `target` CHECK 와 일치).
21. 6단계 중 sections.py·codes.py 수정본을 스크래치에 보관해 A 의 관문 실행을 흔들지 않았다(A 커밋 뒤 복귀). `service/{rules,courses,files}/__init__.py` 독스트링을 구성요소 목록으로 고쳤다.
22. 보고만: `ruff format --check` 로 보면 기존 `app/errors.py`·`app/middleware.py` 가 포맷 밖이다(`make lint` 는 check 만 돌려 통과). 손대지 않았다 → 승인자 판단(도구·규약 묶음).

**리뷰 반영**
23. (리뷰 Nit 2) 첨부 넣기·지우기(`service/files/attachments.py`)는 course 행을 잠그지 않는다. 경합 범위는 계획대로 입장·코드 관리·강의 삭제이고, 관리자 둘의 넣기 vs 삭제 경합은 23503 → 500(재시도 204)으로 드러난다. T6 이 첨부 쓰기 경로를 `lock_course` 로 들일지 정한다(plan.md T6 행 메모).
24. (리뷰 Nit 1·4·5) `5a1a3ed` 로 반영: description 제어 문자 422 · `resume_invite_code(course_id)` 서명 통일 · 65자 초과 코드 malformed. 시험 수 178 → 179(`test_admin_attachment_description_control_char_422` 추가, `test_enter_malformed_code_422` 에 65자·256자, 단위 시험 긴 입력 1줄). 이로써 첨부 description 은 한 줄 글자가 됐다(줄바꿈도 제어 문자라 422; T2a 세션 description 은 LongText 로 여러 줄). 여러 줄이 필요하면 T6 에서 다시 정한다 → 승인자 판단. 반영 뒤 리드 `make verify` exit 0 `179 passed in 7.45s` · OKF guard OK.




---

# Resources

- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §1 · §2 가정 6 · §4 수명·만료 · §5.2 T2b 행 · §6 E-8·E-10·E-11·E-13·E-14 · 부록 A1·A2·A4·A5 · B T2b(엔드포인트 302행 · 시험 세부 315행) · C(0004 331행 · owner_kind 등록 순서와 소유자 삭제 340행) · D(동시성 픽스처 353행 · 폭발 반경 354행) · F(무차별 대입 459행). 저장소 루트 기준 경로이고 `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 저장소 문서: [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) · [`docs/process/plan.md`](../process/plan.md) · [`docs/process/spec.md`](../process/spec.md) · [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md) · [`docs/process/adr/ADR-003-external-ports.md`](../process/adr/ADR-003-external-ports.md) · [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · [`docs/plans/T1-common-base.md`](T1-common-base.md)(리뷰 nit 2 이관) · [`docs/plans/T2a-open-course.md`](T2a-open-course.md)(형식 본보기 · 결정 iii·vii).
- 백엔드 안내서 `2026-10-21-backend-framework-porting-guide.md` §3.1 · §3.2(가드·Text+CHECK) · §3.5 · §7-12(저장소 루트).
- 외부 정본(미추적): `기획/BCTONE_기획안_v3.html` 원칙 5 · 5-4 · P3 · I4 · L1 · 7절 · `시안/학습자.html` 627 · 663 · 669-698 · 704 · 720 · 724 · 753 · 786-788.
- 코드(T2a 가지 머리 `a762cb4`): T1 `src/classfit/{crud/scope.py, crud/auth.py, crud/stored_file.py, service/files/store.py, service/auth/{login,sessions}.py, app/endpoints/files.py, app/deps.py, app/errors.py, core/config.py, models/{auth,stored_file,base}.py}` · T2a `src/classfit/{crud/{course,schedule,invite_code}.py, service/courses/{codes,days,sections}.py, service/rules/{status,invite}.py, app/endpoints/courses.py, schemas/course.py, models/course.py}` · `alembic/versions/0002_common_base.py` · `tests/conftest.py` · `tests/contracts/conftest.py` · `tests/contracts/test_api_admin_guard.py` · `tests/fixtures/courses.py` · `pyproject.toml`.
