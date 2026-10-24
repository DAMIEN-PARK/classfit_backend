---
type: Design
title: "Design: ClassFit 1차 백엔드 — 결정·ERD·공통 규칙·규칙 ↔ 시험"
description: 1차 백엔드의 확정 결정, 인증 갈래, 외부 포트, 마이그레이션별 ERD, T 열이 있는 공통 규칙표, 그리고 check_docs 가 읽는 규칙 ↔ 시험 이름 대응표를 담은 설계 정본
date: 2026-10-21
tags: [design, classfit, backend, erd, rules, phase1]
Archives: false
URL: ""
---

# Design: ClassFit 1차 백엔드

- 상태: 승인 (2026-10-21, r3 플랜 승인 · 승인자 `DAMIEN-PARK`). T0b 에서 r3 의 결정·표·규칙을 이 문서로 옮겼다.
- 정본 범위: 1차의 규칙·표·결정이다(r3 §0 "정본"). 제품은 기획안 v3 이 정본이다.
- **엔드포인트는 `/v1/openapi.json` 이 정본이다.** 이 문서는 엔드포인트를 적지 않는다(r3 §4 "API 정본", src/classfit/main.py:54). 태스크 계획의 경로 목록은 예정이고, 병합 전에 `tests/contracts/expected_paths.txt` 와 OpenAPI 경로 집합이 같아야 한다.
- 출처: r3 §4 · 부록 C · 부록 D · 부록 A4 · 부록 B 의 시험 세부. r1 B0~B2 는 r3 와 다를 때 r3 를 따랐다.
- 바꾸는 법: [spec.md](spec.md) 4절. 규칙이 바뀌면 같은 커밋에서 부록 A 대응표도 고친다.
- 연결: [intent](intent.md) · [feature intent](intents/2026-10-21-phase1-backend.md) · [시안 검토](research/2026-10-21-mockup-review.md) · [plan.md](plan.md)

## 1. 결정 (r3 §4, 플랜 승인으로 확정)

| 결정 | 내용 · 대가 | 기록 |
|---|---|---|
| 학습자 세션 | 토큰은 강의 하나에 묶인다. 다른 강의는 그 강의 코드 + 이메일로 다시 들어온다. 같은 이메일은 같은 `learner` 로 묶고, 표시 이름·부서는 강의마다 `enrollment` 에 둔다. 입장 실패 이유는 기획안 P3 대로 보인다. 대가는 강의마다 재입장, 입장 이유 노출, 유출 대응은 재발급뿐 | [ADR-002](adr/ADR-002-learner-session.md) |
| 외부 포트 | 파일은 Bearer + 범위 판정 뒤 바이트로 주고 응답에는 불투명 `href` 를 둔다. 바이트는 sha256 내용 주소, gc 는 참조 0 ∧ mtime 24시간. 메일은 outbox(kind + params). PDF·HTML 패키지 열기는 501. 대가는 출시 전에 발송 워커·요청 제한이 선행된다는 것 | [ADR-003](adr/ADR-003-external-ports.md) |
| 시안 | 참고 자료로만 쓴다. 시안 JS 는 golden 출처다 | [ADR-001](adr/ADR-001-mockups.md) |
| 공개홈 | 화면은 보류하고 API 는 P3·P4·P5·P6 를 만든다. P2 는 질의 함수까지. r3 §7-1 답에 따라 다시 본다 | [ADR-004](adr/ADR-004-public-home.md) |
| API 정본 | 엔드포인트 모양은 `/v1/openapi.json` 이다. 이 문서는 엔드포인트를 적지 않는다. `tests/contracts/expected_paths.txt` 와 OpenAPI 경로 집합이 같아야 병합된다 | r3 §4 |
| 고객사 표기 | 회사의 정본은 Company 다. `course.client_name` 은 개설 시점 표시용 복제본(필수), `course.company_id` 는 선택 연결이다(기획안 7절) | r3 §4 |
| 만족도 공개 범위 | 강사(I7)·관리자(A5) 결과 모두 개인과 연결하지 않는다. 이름·이메일·enrollment·제출 시각이 없다(원칙 10). 최소 응답 수 임계는 I7 에만 둔다. 관리자는 응답 수를 함께 본다 | r3 §4 |
| 서류 시드 | `document_type` 시드는 기획안 3종이다(r3 §7-2 기본값) | r3 §4 |
| OKF 종류 | 문서 종류 규칙은 `docs/okf.toml` 에 있다(r3 부록 E7) | r3 §4 |

**수명·만료.** 기획안에 근거가 없는 값은 제안값이고, 설정 칸 하나로 바꾼다(r3 §4).

| 칸 | 값 | 근거 |
|---|---|---|
| 관리자 세션 | 8시간 | 제안 |
| 강사 세션 | 14일(설정 칸 `instructor_session_days`) | 제안 |
| 수강생 세션 | 1일. 종료 후 복습 때마다 재입장한다 | 승인자 답(r3 §1.1 ④) |
| 인증 코드 | 10분(설정 칸 `email_code_minutes`), 5회 시도(`email_code_max_tries`). 수명 기준은 해시를 저장한 시각(`email_verification.issued_at`)이고 "지금" 은 DB `now()` 다. 다시 발송하면 새 코드가 옛 코드를 무효로 만들고 시도 수가 0 이 된다 | 제안 · T3 계획 결정 ii·xvi |
| 로그인 잠금 | 같은 (계정, 클라이언트 주소)에서 15분 안 10회 실패면 그 쌍만 15분 차단. 잠긴 요청은 429 + `Retry-After`(잠금 분 × 60초) | 제안 |
| 초대코드 만료 | 강의 종료일 + 30일(설정 칸 `invite_expiry_days`). 발급 때 만료일을 저장하고, 강의 기간이 바뀌어도 따라가지 않는다. 바꾸려면 관리자가 코드를 PATCH 한다. 재발급은 옛 행의 만료일·정원을 새 행으로 옮긴다 | 기획안 5-4 · T2a 계획 착수 조건 결정 (ii) |
| 진단 링크 만료 | 발급 + 14일 | 기획안 8-4 |
| 설문 닫힘 | 강의 종료일 + 14일(설정 칸 `survey_close_days`, T8) | 기획안 8-2 |
| 문의 중복 창 | 1분 | 기획안 P6 |
| I7 최소 응답 수 | 5건(설정 칸 `survey_min_responses`, T8) | 제안 |
| 파일 gc 유예 | 24시간 | 제안(r3 변경 기록 N6) |

## 2. 인증 갈래

r1 B1 의 표를 r3 태스크 번호로 옮겼다.

| 갈래 | 자격 | 저장 | T |
|---|---|---|---|
| 관리자 | 아이디 + 비밀번호(A0). 첫 계정은 `python -m scripts.create_admin`(getpass, 미리 보기 기본, `--apply`) | `admin_account`, argon2id 해시(argon2-cffi `PasswordHasher` 기본형) | T1 |
| 수강생 | 코드 + 이메일. 비밀번호 없음(원칙 2). 새 사람이면 이름과 부서 | `learner`(이메일만) · `enrollment`(이름·부서) | T2b |
| 강사 | 이메일 + 비밀번호. 가입은 이메일 인증 코드 → 정보 → 분야 1개 이상 → 약관 동의(판본 기록, 기획안 P4) | `instructor`(argon2id) · `email_verification`(이메일당 열린 요청 1행) | T3 반영 |
| 진단 응답자 | URL 의 토큰 자체. 세션 없음 | `diag_link` | T9a |

- 관리자·강사·수강생은 `auth_session` 표 하나를 쓴다. 불투명 토큰을 sha256 으로 저장하고 `principal_type`·만료·폐기 칸을 둔다. 전달은 `Authorization: Bearer` 다.
- 수강생 행은 `course_id` 가 있어야 한다(CHECK, ADR-002).
- 정지 강사는 로그인부터 막는다(403). 반려 강사는 로그인되고 사유를 본다(r1 B1, 기획안 P4).

## 3. 외부 포트

결정은 [ADR-003](adr/ADR-003-external-ports.md) 에 있다. r1 B2 의 표를 r3 값으로 옮겼다.

| 포트 | 1차 | 미구성일 때 | 2차 |
|---|---|---|---|
| 파일 저장 | 로컬 디스크 `FILE_STORE_ROOT`(예 `var.nosync/files`, gitignore). sha256 내용 주소, 응답은 `href` | 파일 기능만 501. `FILE_SIGNING_KEY` 는 예약 칸이라 `missing()` 목록 밖이다 | 객체 저장소, 서명 URL |
| 메일 | 같은 요청 트랜잭션에 `mail_outbox` 1행(kind + params). 보내지 않는다 | 문의 수신 주소 `INQUIRY_NOTIFY_TO` 가 없으면 문의 접수만 501 | 발송 워커. import-linter 계약 ①·③ 에 같이 더한다 |
| PDF | 진단 PDF 는 501. 리포트는 JSON 으로 준다 | 501 | 서버 생성(기획안 11절 3번) |
| HTML 패키지 | zip 보관만. 열면 501. T6: 첨부 zip 은 보관만, `GET /v1/files/{key}` 가 범위 판정 뒤 501 `/problems/not-implemented` | 501 | 별도 출처 정적 호스팅(r3 §7-5) |
| xlsx 내보내기 | 없음. JSON 으로 준다 | 해당 없음 | 의존성 승인 뒤 |

## 4. 데이터 (ERD)

이름·키·소유 관계만 적는다. 칸은 태스크 계획에서 정하고, 마이그레이션은 슬라이스대로 한 줄기로 쌓는다(r3 부록 C).

| 마이그레이션 | T | 표 (PK · 유일 · FK) |
|---|---|---|
| 0002 | T1 | `admin_account`(id · login_id U) · `auth_session`(id · token_hash U · principal_type · principal_id · course_id, CHECK learner ⇔ course_id 있음) · `auth_attempt`(id · kind · subject_hash · client · at · ok) · `mail_outbox`(id · kind · params · to · sent_at) · `stored_file`(id · key U · sha256 · owner_kind · owner_id) · `email_verification`(id · code_hash NULL 허용 · tries, 0005 에서 앞당김) |
| 0003 | T2a | `course`(id · client_name · status · status_manual) · `course_day`(course_id+day_no U) · `section`(course_id) · `session`(section_id · day_no · slot) · `invite_code`(course_id · code U 전 행 · course_id 부분 U where status≠replaced) · FK `auth_session.course_id→course` |
| 0004 | T2b | `session_attachment`(session_id · kind 5종 pdf·office·html·link·image · title · description · file_id→stored_file U 또는 url, CHECK link ⇔ url 있음 ∧ link 면 file_id 없음 · sort, FK 둘 다 NO ACTION) · `learner`(email U lower, 이름 없음) · `enrollment`(course_id+learner_id U · name · dept, FK 둘 다 NO ACTION) |
| 0005 | T3 | `instructor`(email U lower · status 4값 · reject_reason, CHECK 반려 ⇔ 사유 있음 · terms_version · terms_agreed_at) · `email_verification` 에 `email` NOT NULL · `issued_at` · `consumed_at` · `instructor_id`(FK NO ACTION) 와 부분 U lower(email) where consumed_at IS NULL(표는 0002) · `tag`(kind+name U · group_name 은 field 만, 6값) · `instructor_tag`(PK 쌍, instructor FK CASCADE) · `document_type`(id text, 시드 resume·cert·pledge) · `instructor_document`(instructor_id+type_id U · file_id→stored_file U, FK 셋 다 NO ACTION). 서류의 `stored_file.owner_id` 는 강사 id 다 |
| 0006 | T4 | `pool_course`(id text · source ax·own · owner_instructor_id, CHECK own ⇔ 소유 강사 있음 · job_groups text[] ≥ 1 · difficulty 하·중·상 · minutes · theory·practice text[] · schedule jsonb · 플래그 reviewed·pub·active · reviewed_at) · `pool_course_file` · `capability`(instructor_id+pool_course_id U · memo) · `capability_file` · `curriculum`(id text · instructor_id · days 1~30 · start_time < end_time · slot_min · break_min · 플래그 셋 · reviewed_at) · `curriculum_slot`(curriculum_id+day+slot U, CASCADE) · `curriculum_file` · `advanced_course`(id text · hours · features ≤ 5 · pub·active) · 시퀀스 `pool_id_seq`(id 번호). 파일 표 셋은 칸이 같다(kind 5종 · file_id→stored_file U 또는 url). FK 는 차시만 CASCADE, 나머지는 NO ACTION. 시드 없음. 상태는 열거형이 아니라 불리언 셋이고 `pub ⇒ reviewed` 는 CHECK 가 아니라 service 규칙이다(T4 결정 v·vi). T4 반영 |
| 0007 | T5 | ALTER `session` + pool_course_id · curriculum_id · instructor_id · ALTER `course` + curriculum_src_id · ALTER `session_attachment` + origin(NULL · CHECK 원본 owner_kind 셋) · T5 반영(NULL 허용 · FK NO ACTION · `ix_session_instructor_id`) |
| 없음 | T6 | 0004 의 `session_attachment` 를 쓴다 · T6 반영(파일 넷·링크 · 교체는 같은 행 file_id 바꿈 · `origin` 은 강사 응답에만) |
| 0008 | T7 | `session_record`(session_id U) · `photo`(course_id · session_id · file_id) · T7 반영(세션당 기록 1행 · 기록 FK CASCADE · 사진 FK NO ACTION · 기록자·올린 사람 칸 FK 없음 · 공개 칸 없음) |
| 0009 | T8 | `survey_template` · `survey`(course_id 부분 U where open · template_id SET NULL) · `survey_response`(survey_id+enrollment_id U) · T8 반영(부분 U 는 `current` 칸 — 상태는 open_on·close_on·closed_at 과 오늘로 계산 · 문항·양식 이름 스냅샷 · course FK CASCADE · 응답 (설문, 등록) U · submitted_at 비노출 · 기본 양식 시드 1행) |
| 0010 | T9a | `company` · `diagnosis`(company_id+round_no U) · `diag_link`(token U · company_id 부분 U where open) · ALTER `course` + company_id(선택) · T9a 반영(회사 삭제는 회차·링크 CASCADE · 부서 ≤ 20 · 링크 토큰 평문 U · open 부분 U `uq_diag_link_company_open` · 만료는 계산 · `course.company_id` ON DELETE SET NULL) |
| 0011 | T9b | `inquiry`(Company 연결 없음) |

- `stored_file.owner_kind` 등록 순서: T2b session_attachment(T2b 등록됨. 관리자 참 · 수강생은 같은 강의 ∧ 세션 `is_open`, `crud/scope.py` · T6: 강사는 범위 강의의 내 세션 ∨ 열린 세션) · T3 instructor_document·instructor_photo(T3 등록됨. instructor_document 는 본인 강사만 — 종류와 id 를 함께 보고 관리자는 거짓, 관리자 열람은 audit 끝점 · instructor_photo 는 관리자 ∨ 본인 강사, 행을 만드는 끝점은 아직 없다) · T4 pool_course_file·capability_file·curriculum_file(T4 등록됨. 세 종류 다 owner_id = 파일 행 id 이고 관리자 ∨ 본인 강사 — 주체 종류를 먼저 본다(`crud.scope.owned_by`), 관리자 열람에 audit 은 없다) · T7 photo(T7 등록됨. 관리자 ∨ 그 세션의 지금 담당 강사, 수강생 거짓 — 공개 표시 없음) · T9a diagnosis_pdf(T9a 등록됨. 관리자만. 행을 만드는 끝점은 없다 — PDF 501). 등록되지 않은 종류는 404 다.
- 다형 참조라 FK 가 없다. 그래서 소유자 행을 지우는 crud 는 같은 트랜잭션에서 stored_file 행도 지운다.
- head 는 정확히 하나다. 1차 끝에 `alembic heads` 가 `0011 (head)` 한 줄이다(r3 §6 E-8).

## 5. 공통 규칙

r3 부록 D 가 본문이다. r1 B0 의 규칙은 r3 와 겹치지 않는 것만 더했다. T 열은 규칙이 처음 코드로 들어오는 태스크다. 이 표는 기계가 읽지 않는다. 기계가 읽는 표는 부록 A 다.

| # | 규칙 | 내용 | T | 근거 |
|---|---|---|---|---|
| 1 | 재사용 부품 | `DbSession`(app/deps.py) · `NotFound·Forbidden·Conflict·Gone·NotConfigured`(core/errors.py:22-43) · `AppError·unauthorized()·forbidden()`·`problem()`(app/errors.py:38-91) · `insert_audit`(crud/audit.py:12) · `Base·BigIdMixin·TimestampMixin`(models/base.py:26-44) · `ROUTERS`(app/routers.py:5) · 계약 픽스처 `app·client·client_noraise`(tests/contracts/conftest.py:42-65). 경계 시험의 본보기는 test_tx_boundary.py 다. 시험 전용 라우터는 probe_routes.py 처럼 ROUTERS 밖에 둔다 | T1 부터 전부 | r3 부록 D |
| 2 | 경로 규칙 | 관리자 `/v1/admin/…`, 강사 `/v1/me/…`, 수강생 `/v1/learner/…`, 토큰 `/v1/ax/{token}`. 동작은 `:접미사`. 목록은 커서 `{items,next_cursor,has_more}`. 파일을 가리키는 응답 칸은 `href` | T1 부터 전부 | r3 부록 B 머리 · r1 B0 |
| 3 | 권한 | 목록·파일 조회의 첫 WHERE 는 주체 범위다(`crud/scope.py`). 남의 자원은 403, 등록 안 된 파일 소유 종류는 404. T6: `session_scope`(강사는 맡은 세션) · 명단·첨부 목록 `list_stmt`·`_listed` 는 강사 주체면 ValueError. T7: 강사 기록 목록·사진 목록의 첫 WHERE 는 `session_scope`(내 세션), 모아보기는 `course_scope`. T8: 설문 목록·홈·포털 `survey` 칸의 첫 WHERE 는 `course_scope`, 수강생은 토큰의 강의(403), 강사 결과는 배정 강의(404 → 403). T9a: 회사 목록의 첫 WHERE 는 `company_scope`(관리자 전부 · 그 밖 거절), 공개 토큰 끝점(`/v1/ax/{token}`)은 주체가 토큰 | T1 부터 전부 | r3 부록 D · T6 계획 결정 xxii · T7 계획 결정 ix·x·xi · T8 계획 결정 i·xiv·xv·xvi · T9a 계획 결정 ix |
| 4 | 트랜잭션 | 요청 1개 = 트랜잭션 1개(`db()`). service·crud 는 flush 까지만 하고 commit 하지 않는다 | 전부 | CLAUDE.md Rules |
| 5 | 유일 위반 | `flush_or_conflict(session, message, *rows)` 는 begin_nested 안에서 rows 를 add 하고 flush 한다. SQLAlchemy 2.0.55 의 `begin_nested()` 는 SAVEPOINT 를 열기 전에 대기 변경을 flush 하므로, 위반이 날 수 있는 행은 rows 로 넘겨 SAVEPOINT 안에서 add 한다. `exc.orig.sqlstate == '23505'` 일 때만 Conflict(409)로 바꾼다. CHECK(23514)·FK(23503) 등은 다시 던져 500 이 된다 | T1 | r3 부록 D · N5 |
| 6 | 세고 넣는 경쟁 | 정원·재발급·열린 설문은 대상 행을 FOR UPDATE 로 잠근다. T2b 의 잠금 대상은 바뀌는 코드 행이 아니라 고정된 `course` 행이다(`crud.course.lock_course`, 잠그며 populate_existing 으로 다시 읽는다). 입장 · 코드 행을 바꾸는 네 문(재발급·정지·재개·수정) · 강의 삭제가 맨 앞에서 잠그고, 잠금 순서는 course → invite_code → learner·enrollment·auth_session 이다. 입장은 잠그기 전에 코드로 course_id 스칼라만 읽고, 잠근 뒤 코드 행을 populate_existing 으로 다시 읽는다(잠금을 기다린 사이의 재발급·정지를 identity map 이 가리지 않게). T3: 강사 상태 전이(approve·reject·suspend·unsuspend·reapply)와 강사 로그인의 상태 판정은 `instructor` 행 FOR UPDATE(`crud.instructor.lock_instructor`) 뒤다. 로그인은 비밀번호 대조 뒤에 잠근다. 잠금 순서는 advisory(`lock_attempt_key`) → instructor → auth_session·mail_outbox·audit_log 이고, 잠금이 있는지는 정적 시험 `test_instructor_status_lock_call_sites` 가 본다(동시성 시험은 두지 않는다). T4: 커리큘럼 차시표 교체·수정은 `curriculum` 행 FOR UPDATE(`crud.curriculum.lock_curriculum`) 뒤에 판정한다(격자 축소 검사도 잠근 뒤 읽는다). 잠금 순서는 curriculum → curriculum_slot 이고 정적 시험 `test_pool_curriculum_lock_call_sites` 가 본다. 고유 과정 PATCH·관리자 플래그 PATCH·파일 개수 상한은 잠그지 않는다(결정 xxii). T5: 전체 잠금 순서는 curriculum(원본 FOR UPDATE · 참조 FOR KEY SHARE) → 참조 pool_course(FOR KEY SHARE) → course → instructor → (강사, 과정) 묶음마다 원본 capability(FOR KEY SHARE) → 원본 stored_file(FOR SHARE, id 오름차순)(묶음 사이 순서는 섞일 수 있으나 모두 공유 잠금이고, 배타 쪽 역량 삭제·파일 한 개 삭제는 한 묶음만 건드려 고리가 없다) → 새 행이다 — 세션 행을 넣는 경로는 FK 검사가 잡을 참조 행을 강사보다 먼저 id 순으로 잡는다. T2a `days.py`·`sections.py` 의 쓰기 함수 전부(열 개)와 T2b 첨부 넣기·지우기도 맨 앞 `lock_course` 아래다(PDF 는 바이트 쓰기 뒤) — 두 파일의 잠금 순서는 전부 course → 일차·섹션·세션 행이다. 행동 시험 여덟은 `tests/integration/test_db_assign_race.py`(E-11 밖). T6: 강사 첨부 쓰기 다섯은 맨 앞 `lock_course`(파일은 바이트 쓰기 뒤) → 잠근 뒤 첨부·세션 다시 읽기 → session_attachment → stored_file. 행동 시험 일곱은 `tests/integration/test_db_attachment_race.py`(E-11 밖). T7: 기록·사진 쓰기는 맨 앞 `lock_course`(사진은 바이트 쓰기 뒤) → 잠근 뒤 세션·일차·기록·사진 다시 읽기 → session_record·photo → stored_file → audit. 확인 표시는 강의를 잠그지 않고, 사진 여러 행을 잡는 쓰기(확인 표시 · 세션·섹션·강의 삭제의 사진 지우기)는 같은 id 순 FOR UPDATE 로 잡는다. 행동 시험 일곱은 `tests/integration/test_db_record_race.py`(E-11 밖). T8: 배포는 양식 KEY SHARE → 강의 id 오름차순 `lock_course` → 현재 설문 `lock_survey` → fresh 판정 → supersede → insert(부분 유일 뒷받침) · 닫기·다시 열기·PATCH 는 `lock_course` → `lock_survey` → fresh 상태·응답 수 → 쓰기 · 제출은 `lock_survey` → fresh 상태·기존 응답 → insert · 양식 삭제는 양식 FOR UPDATE → 참조 강의 id 순 `lock_course` → survey id 순 FOR UPDATE · 강의 삭제도 `lock_course` 뒤 survey id 순 FOR UPDATE. 순서 template(KEY SHARE) → course → survey → survey_response. E-11 에 `test_concurrent_survey_deploy_one_open`, 행동 시험 열은 `tests/integration/test_db_survey_race.py`(E-11 밖). T9a: 회사·회차·링크 쓰기는 맨 앞 `lock_company`(FOR UPDATE) → 잠근 뒤 회차·링크 다시 읽기 → diagnosis·diag_link → audit. 회사 PATCH 도 `lock_company` 로 잡아 다시 읽은 뒤 바뀐 칸만 쓴다(지우기와 엇갈리면 404). 개설(①②③④ 의 회사 연결)은 `hold_company`(FOR KEY SHARE) → course. company 는 T5 순서의 참조 행 층(①′)이다. 회사 삭제만 밖을 기다린다 — `lock_company` 뒤 연결 강의(보관 포함)를 `lock_linked_courses` 로 id 오름차순 FOR UPDATE 로 먼저 잡고(그 강의 행을 쥔 `lock_course` 보유자를 여기서 기다린다) 연결을 풀고 지운다. 순서는 company → course(id 오름차순)라 강의를 id 순으로 잡는 T8 양식 삭제와도 고리가 없고, `lock_course` 보유자는 company 를 잡지 않는다. 행동 시험 아홉은 `tests/integration/test_db_diag_race.py`(E-11 밖) | T2b · T3 · T4 · T5 · T6 · T7 · T8 · T9a | r3 부록 D · T2b 계획 결정 ii·v · T3 계획 결정 vi·viii·xix · T4 계획 결정 xix·xxii · T5 계획 결정 xvii·xviii · T6 계획 결정 xv·xvi · T7 계획 결정 xiii·xiv · T8 계획 결정 xix · T9a 계획 결정 xi·xvi |
| 7 | 실패해도 남는 쓰기 | 실패한 로그인·인증 코드 끝점은 같은 요청 트랜잭션에 `auth_attempt` 1행을 쓰고, 예외 대신 `problem()` 으로 401·422 를 반환한다. 그래서 `db()` 가 커밋한다. 대가: 그 끝점은 실패 판정 전에 다른 쓰기를 하지 않는다. 잠금 판정 키는 (계정, `request.client.host`) | T1 | r3 부록 D · N4 · N10 |
| 8 | 인증 코드 | 생성은 `classfit.service.auth.email_code` 의 `issue_email_code(session, verification_id)` 한 함수다(구성요소 폴더라 하위 모듈로 풀었다). 요청은 outbox 에 kind=`email_code`, params={verification_id} 만 쌓는다. `scripts.outbox_preview` 는 미리 보기면 본문을 찍고 롤백하며 "무효 코드(미리 보기)"라고 찍는다. `--apply` 면 해시를 저장하고 sent_at 을 채운다. 다시 보내면 새 코드가 이전 해시를 덮는다. T3: 해시를 저장할 때 `issued_at` 도 `now()` 로 쓰고, 수명은 그 시각부터 잰다(지금은 DB `now()`). 강사 가입의 요청·가입 끝점과 `service/instructors` 는 코드를 만들지 않는다. 새 outbox kind `instructor_approved`·`instructor_rejected` 의 params 는 {instructor_id, audit_id} 이고, 반려 사유는 params 가 아니라 audit detail(불변)에서 렌더러가 읽는다 | T1 · T3 | r3 부록 D · N13 · T3 계획 결정 ii·vi·xvi |
| 9 | 파일 바이트 | 업로드는 sha256 경로에 바이트가 없으면 쓰고, 있으면 mtime 만 갱신한다. 행은 요청 트랜잭션에 넣는다. `scripts.file_gc` 는 참조 행 0 ∧ mtime 24시간 지난 바이트만 지운다(미리 보기 기본, `--apply`). T5: 기본 강의안 사본은 행만(같은 sha 다른 key), 바이트 I/O 없음. 원본 `stored_file` 행을 복사 커밋까지 FOR SHARE 로 잡아, 원본 삭제·gc 가 사본 커밋 전에 바이트를 지우지 못한다(유예는 mtime 기준이라 오래된 원본을 지키지 못하므로). 사라진 원본은 `skipped_missing`. T6: `test_gc_grace` 가 강사 업로드의 '바이트 있음 ∧ 행 없음' 순간을 잰다 | T1 · T5 · T6 | r3 부록 D · N6 · T5 계획 결정 x · T6 계획 결정 xvii |
| 10 | 응답 모양 | 파일은 `href`(지금은 `/v1/files/{key}`)로 가리킨다. 서명 URL 로 바꿔도 칸 이름과 타입이 같다 | T1 · T2b | r3 부록 D · N12 |
| 11 | 소유자 삭제 | 소유자 행을 지우는 crud 는 같은 트랜잭션에서 stored_file 행도 지운다. T2b: 첨부의 `session_id`·`file_id` FK 가 NO ACTION 이라 세션·섹션·강의 삭제 경로가 지우기 전에 첨부 행 → 그 첨부가 소유한 stored_file 행을 먼저 지운다(`crud.attachment.delete_attachments_under`). 강의 삭제는 `service.courses.remove.remove_course` 한 곳이고, 수강생이 있으면 409, 없으면 그 강의의 auth_session 행(만료·폐기 포함)도 먼저 지운다(`crud.auth.delete_course_sessions`, 0003 FK NO ACTION). 바이트는 gc 가 지운다. T3: 서류 교체는 새 stored_file 행 → 서류의 file_id 바꿈 → 옛 stored_file 행 삭제를, 서류 삭제는 서류 행 → stored_file 행을 같은 트랜잭션에서 한다(`service.files.documents`). `instructor_document`·`email_verification` 의 instructor FK 는 NO ACTION 이라 강사 행을 지우는 길은 그 행들을 먼저 지워야 한다(1차에 강사 삭제 끝점은 없다). T4: 역량 삭제는 역량 파일 행 → 그 stored_file 행 → 역량 행, 풀 파일 삭제는 파일 행 → 그 stored_file 행을 같은 트랜잭션에서 지운다(`crud.pool_file`·`crud.capability.delete_capability`). 고유 과정·커리큘럼의 "삭제" 는 active=false 라 행·역량·파일이 남는다. T5: 사본도 `session_attachment` 행이라 기존 삭제 경로가 지운다. 출처는 `session_attachment.origin`(NULL = 보통 첨부). T6: 첨부 교체는 새 stored_file → file_id 바꿈 → 옛 stored_file 행 삭제(같은 트랜잭션, 옛 행은 잠근 뒤 읽은 file_id), 바꾸면 origin NULL. T7: 사진 지우기는 사진 행 → stored_file 행, 세션·섹션·강의 삭제는 첨부 다음에 `crud.photo.delete_photos_under`, 기록은 세션 FK CASCADE | T2b 부터 | r3 부록 C · T2b 계획 결정 ix·xi · T3 계획 결정 ix · T4 계획 결정 x·xi · T5 계획 결정 xi · T6 계획 결정 vii · T7 계획 결정 iv·xvi |
| 12 | 상태 열 | `Text + CheckConstraint` 로 둔다. 마이그레이션 리비전 id 는 손으로 매긴다(0002, 0003 …) | T1 부터 전부 | r1 B0 |
| 13 | 단일 진입점 | 강의 개설 + 코드 발급은 `open_course()`(`classfit.service.courses.open`. 시작점 ②④ 도 그 안에서 처리해 단일 진입을 지킨다, T5 · 시작점 ③(확정 진단)도 그 안 `service/courses/start_diagnosis.py`, T9a), 초대코드는 `issue_invite_code()`(`classfit.service.courses.codes`. 생성 도우미 `_new_invite_code` 는 그 파일 밖에서 부르지 않는다), 인증 코드는 `issue_email_code()`(`classfit.service.auth.email_code`) 로만 만든다. 강사 행은 `signup()`(`classfit.service.instructors.signup`)만 `insert_instructor` 로 만든다(`test_instructor_created_only_in_signup`). 풀 과정 행은 `insert_pool_course` 를 `service/pool/{own,admin,catalog_import}.py` 만 부른다(`test_pool_course_created_only_in_service`) | T1 · T2a · T3 · T4 · T5 · T9a | r3 부록 E7 · T5 계획 결정 iii · T9a 계획 결정 vii |
| 14 | 구성요소·import 경계 | `service/rules`(최하위 순수 함수 `course_status_at·code_state_at·make_days·session_time`) · `service/auth` · `service/courses`(`open_course`·`issue_invite_code`). 계약 ② 는 T1 에 `type = "independence"`(`classfit.service.auth`·`classfit.service.files`)로 처음 더했고, T2a 에서 `type = "layers"`·containers `classfit.service`·exhaustive 로 바꿨다. 위층은 서로 독립인 `auth`·`courses`·`diagnosis`·`enroll`·`files`·`instructors`·`pool`·`surveys`(T2b 가 입장 판정 `enroll` 을, T3 가 가입·프로필·상태 전이 `instructors` 를, T4 가 과정 풀·역량·커리큘럼·심화·import `pool` 을, T8 이 양식·배포·응답·집계 `surveys` 를, T9a 가 회사·진단 회차·링크·공개 응답·리포트 `diagnosis` 를 더했다), 아래층은 `rules` 다. 새 구성요소 폴더는 ② 에 더하기 전엔 lint-imports 가 막는다. rules 가 crud·models·DB 를 부르지 않는 것은 계약이 아니라 `tests/unit/test_import_rules.py` 가 본다. 계약 ① 이 exhaustive 라 1차에는 새 최상위 모듈을 만들지 않는다. 구성요소 사이의 읽기는 crud 를 거친다 | T1 부터 | r3 부록 D · r1 B0 |
| 15 | 날짜 | 날짜는 `Today`(Asia/Seoul) 한 곳에서 받고 시험이 `app.dependency_overrides[classfit.app.deps.today]` 로 주입한다. 상태 판정 함수는 오늘을 인자로 받는다. T8: 설문 열림·닫힘은 날짜라 상태를 `Today` 로 판정한다(워커 없음) | T1 부터 | r3 §2 가정 5 · T8 계획 결정 iii |
| 16 | 원본 한 곳 | 문항·산식·상태 규칙은 코드 한 곳에 둔다. 진단 A4 와 자가진단 P5 가 같은 원본을 쓴다. T9a: 문항 `service/rules/diagnosis_items.py`·`diagnosis_items_34.py`(데이터 두 파일, 300줄 상한) · 산식·전이 `diagnosis.py` · 권장 구성 초안·부서 → 직무군 매핑 `reco.py`(후보는 T4 카탈로그의 공개 AX 과정) | T2a · T9a | r3 §3 원칙 ② · T9a 계획 결정 v·viii·xv |
| 17 | golden 추출 | `scripts/golden/extract.mjs` 는 시안 JS(`scTime·scMakeDays·calc`)를 node 로 돌려 숫자·날짜·시각만 대조 대상으로 남긴다. 입력은 extract.mjs 가 만든 합성 사례라 회사명·인명이 처음부터 없다. 시간대는 첫 줄에서 Asia/Seoul 로 고정해 기계 시간대와 무관하다. 재추출 대조는 `scripts/golden/check.sh`(pre-push) 한 곳이고, CI 는 커밋된 `tests/fixtures/golden.json` 을 쓴다. T5: `scSlotTimes`·`scSlots`(하루 교시 수, `test_golden_schedule_slot_count`). T9a: `AREAS` 블록 + `calc`, 사례 `score` 일곱(`test_golden_score_` 3 — 출력은 숫자만) | T2a · T5 · T9a | r3 부록 D · N8 · T2a 계획 착수 조건 "golden 이름 처리" · T5 계획 결정 xix · T9a 계획 결정 xv |
| 18 | 시험 | 파일 이름은 `test_api_*`·`test_db_*`·`test_*_rules` 이고 basename 이 유일해야 한다(tests/conftest.py:7). 수용 기준이 세는 시험 이름은 부록 A 를 따른다. 동시성 시험은 `tests/integration/test_db_concurrency.py` 에 두고, 커밋하고 끝에 지우는 별도 픽스처를 쓴다. 픽스처는 `migrated_db_url` 로 NullPool 엔진을 따로 만들고, finally 에서 `Base.metadata.sorted_tables` 를 `TRUNCATE … RESTART IDENTITY CASCADE` 한다. 순서는 시간이 아니라 기계로 고정한다: A 가 판정 뒤 커밋 전에 멈춤 → B 태스크 → 제3 연결이 `pg_stat_activity.wait_event_type = 'Lock'` 을 보거나 B 가 끝날 때까지(최대 5초) 기다림 → A 커밋 → B 결과와 "B 가 기다렸다" 를 단언. T2b 는 로그인 잠금(`lock_attempt_key`) 시험도 여기 둔다(T1 리뷰 nit 2 이관). T8: E-11 다섯(`test_concurrent_survey_deploy_one_open`) | 전부 | r3 부록 D · T2b 계획 결정 xiii · T8 계획 결정 xix |
| 19 | 폭발 반경 | T1·T2a·T2b·T3·T4·T5·T6·T7·T8·T9a·T9b 는 시험 + 대조 실험 + verifier, 나머지는 시험 + 대조 실험이다 | 전부 | r3 부록 D · T8 계획 결정 xxiv |
| 20 | 설정 칸 | `FILE_STORE_ROOT`·`INQUIRY_NOTIFY_TO` 는 없으면 그 기능만 501 이다(`Settings.missing()`). 1절 수명·잠금·gc 유예 값은 1절 값을 설정 기본값으로 가지므로 `missing()` 대상이 아니다(ADR-002 결정 5, T1 계획 착수 조건 (ii)). 관리자 첨부 PDF 상한 `ATTACHMENT_PDF_MAX_MB`(기본 50, 기획안 I4, T2b)도 같다. T3 의 `INSTRUCTOR_SESSION_DAYS`(14)·`EMAIL_CODE_MINUTES`(10)·`EMAIL_CODE_MAX_TRIES`(5)·`DOCUMENT_PDF_MAX_MB`(10)도 수명·잠금·상한 꼴이라 같다. `TERMS_VERSION`(기본 "2026-10-22")은 이 규칙의 예외다: 약관 판본은 외부 자원이 아니라 제품 상수에 가까워 기본값을 두고 빈 글자만 막는다(T3 계획 결정 iii, 승인자 기본값 승인). `FILE_SIGNING_KEY` 는 예약 칸이라 `missing()` 밖이다. T4 는 새 설정이 없다: 풀 파일 PDF 상한은 `ATTACHMENT_PDF_MAX_MB` 를 같이 쓴다(T4 계획 결정 viii). T6 의 `ATTACHMENT_OFFICE_MAX_MB`(50)·`ATTACHMENT_ZIP_MAX_MB`(100)·`ATTACHMENT_IMAGE_MAX_MB`(10)도 같다. T7 은 새 설정이 없다 — 사진 상한은 `ATTACHMENT_IMAGE_MAX_MB` 를 같이 쓴다. T8 의 `SURVEY_MIN_RESPONSES`(5)·`SURVEY_CLOSE_DAYS`(14)도 같다. T9a 는 새 설정이 없다 — 링크 만료 14일·토큰 길이·후보 3 은 코드 상수다. `make run` 은 `--no-access-log`(uvicorn 접근 로그가 토큰 경로를 찍지 않게, T9a 계획 결정 xxv) | T1 부터 | r3 부록 D · T3 계획 결정 iii · T4 계획 결정 viii · T6 계획 결정 iv · T7 계획 결정 vii · T8 계획 결정 xxi |




## 부록 A. 규칙 ↔ 시험 이름 대응표

출처는 r3 부록 A4 의 서버 판정 규칙과 부록 B·§5.2 의 시험 세부, 이름 규약은 r3 부록 D 다. `scripts/check_docs.sh` ④ 가 이 표를 읽는다.

- **읽는 모양:** 머리 행은 `규칙 | T | 시험 이름 | 근거` 다. T 칸은 태스크 하나(`T<n>` 또는 `T<n><소문자>`)다. 시험 이름 칸의 백틱 글자가 시험 이름이다.
- **이름 뜻:** 이름이 `_` 로 끝나면 접두다. 그 접두로 시작하는 `def` 가 `tests/` 에 하나 이상 있으면 된다. 아니면 정확히 그 이름의 `def` 가 있어야 한다.
- **검사 대상:** master first-parent 에 `merge: T<n>` 이 있는 T 의 행만 잰다. T0b 시점에는 T0a 만 병합됐고 T0a 행은 없으므로 대상은 0행이다.
- **이름의 출처:** r3 가 정한 이름(`test_p3_*` 9건 · `test_reissue_*` 2건 · `test_cross_course_portal_403` · `test_enrollment_name_isolated` · `test_no_personal_keys_portal` · `test_gc_*` 2건)은 그대로 썼다. 접두 `test_golden_`·`test_no_personal_keys_` 는 r3 부록 D 규약이다. 나머지 접두는 이 문서가 정한 자리 이름이다. 그 T 의 계획이 같은 커밋에서 이 표를 고쳐 바꿀 수 있다.

| 규칙 | T | 시험 이름 | 근거 |
|---|---|---|---|
| 틀린 비밀번호와 없는 아이디가 같은 401 + WWW-Authenticate. 폐기·만료 토큰 401 | T1 | `test_admin_login_` | r3 §5.2 T1 · 부록 B T1 |
| 실패 시도 행은 401 응답 뒤에도 남는다 | T1 | `test_auth_attempt_` | r3 부록 D · N4 |
| 로그인 잠금 키는 (계정, 클라이언트 주소). 다른 주소는 잠기지 않는다 | T1 | `test_auth_lockout_` | r3 §5.2 T1 · N10 |
| 수강생 세션 행에 course_id 가 없으면 CHECK 위반 | T1 | `test_auth_session_` | r3 부록 B T1 · ADR-002 |
| 파일 접근: 미등록 owner_kind 404, 파일 루트 미설정 501, `FILE_SIGNING_KEY` 없어도 200 | T1 | `test_files_` | r3 부록 A4 · 부록 B T1 · ADR-003 |
| 유일 위반만 409, CHECK 위반은 500 | T1 | `test_flush_or_conflict_` | r3 부록 D · N5 |
| 409 로 끝난 요청의 outbox 는 0행 | T1 | `test_outbox_` | r3 §5.2 T1 |
| 인증 코드는 `issue_email_code()` 에서만 만든다. 미리 보기는 해시를 저장하지 않는다 | T1 | `test_email_code_` | r3 부록 A4 · 부록 B T1 · N13 |
| OpenAPI 경로 집합 = expected_paths.txt, `/v1/_probe` 없음 | T1 | `test_openapi_` | r3 §4 · §6 E-13 |
| 코드 생성: 같은 알파벳(0·O·1·I 없음), 전 행 유일, 재발급은 옛 행 replaced | T2a | `test_invite_code_` | r3 부록 A4 · 부록 B T2a |
| 세션 시각·일정은 시안 값과 같다(golden) | T2a | `test_golden_schedule_` | r3 부록 A4 · 부록 D · E-12 |
| 강의 상태: Python 과 SQL 판이 같다, KST 경계(UTC 15:00), `:reset-status` 뒤 날짜 규칙이 다시 이긴다 | T2a | `test_course_status_` | r3 §5.2 T2a · 부록 B T2a |
| 종료 시 코드 정지(`code_state_at`), 종료 강의 `:resume` 409 | T2a | `test_code_state_` | r3 부록 A4 · §5.2 T2a |
| 초대코드 검증(입장): 기획안 P3 표 7행 → 9건 | T2b | `test_p3_active` · `test_p3_preparing` · `test_p3_ended` · `test_p3_expired` · `test_p3_paused` · `test_p3_full` · `test_p3_not_found` · `test_p3_existing_email` · `test_p3_confusable` | r3 부록 B T2b · E-10 |
| 재발급 뒤 옛 코드는 없는 코드와 같은 응답, 기존 수강생 세션은 유지 | T2b | `test_reissue_old_code_not_found` · `test_reissue_keeps_sessions` | r3 부록 B T2b · E-10 |
| 파일 접근: 다른 강의 수강생이 포털·파일 `href` 를 열면 403 | T2b | `test_cross_course_portal_403` | r3 부록 B T2b · ADR-002 |
| 같은 이메일로 다른 강의에 다른 이름을 등록해도 이 강의 명단은 그대로 | T2b | `test_enrollment_name_isolated` | r3 부록 B T2b · N9 |
| 준비 중 카드: `is_open` ∧ 첨부 ≥1 이 아니면 잠김 | T2b | `test_portal_locked_` | r3 부록 A4 · 원칙 5 |
| 포털 응답에 개인 키 없음 | T2b | `test_no_personal_keys_portal` | r3 부록 B T2b · E-14 |
| 정원·재발급 동시성(course 행 FOR UPDATE) · 재발급 뒤 옛 코드 입장 404 · 로그인 실패 세기를 advisory 잠금으로 줄 세움 | T2b | `test_concurrent_enroll_capacity` · `test_concurrent_reissue_one_live` · `test_concurrent_reissue_then_enter_old_code_404` · `test_concurrent_login_failures_serialized` | r3 §5.2 T2b · E-11 · T2b 계획 결정 ii·xiii |
| 강사 상태 전이(기획안 A2 상태표 4행), 사유 없는 반려 422, 정지 로그인 403 | T3 | `test_instructor_status_` | r3 §5.2 T3 · 부록 B T3 |
| outbox 에 인증 코드 평문 없음, 만료 410, 시도 초과 429, 재발송하면 이전 코드 무효 | T3 | `test_instructor_email_code_` | r3 부록 A4 · 부록 B T3 |
| 서류 열람은 audit 1행, 남의 서류 403 | T3 | `test_instructor_document_` | r3 §5.2 T3 · 부록 B T3 |
| 카탈로그는 공개 ∧ 활성만, 강사 이름 없음 | T4 | `test_no_personal_keys_catalog` | r3 §5.2 T4 · 부록 D · E-14 |
| `import_ax_catalog` 를 두 번 돌려도 같다 | T4 | `test_import_ax_catalog_` | r3 §5.2 T4 |
| 강사가 AX 과정을 고치면 403. 검토 뒤 강사가 고치면 reviewed=false, pub·active 유지 | T4 | `test_pool_` | r3 부록 B T4 |
| 기본 강의안 자동 첨부: 행 복제, 같은 sha 다른 key. 복제 시작점은 첨부를 복사하지 않는다 | T5 | `test_default_material_` | r3 부록 A4 · §5.2 T5 · 부록 B T5 |
| 미승인 강사 배정 409 | T5 | `test_assign_` | r3 §5.2 T5 · 원칙 3 |
| 강사는 구조를 만지지 않는다: 제목 PATCH 422, 남의 세션 403 | T5 | `test_instructor_session_` | r3 §5.2 T5 · 부록 B T5 · 원칙 13 |
| 개설 시작점 ②④: 원본을 복제하고(원본을 고쳐도 강의는 그대로, CAT-007), 비활성 커리큘럼·미승인 소유 강사는 409 | T5 | `test_open_course_start_` | T5 계획 결정 iii·iv·v·xxi · 요구정의서 CAT-007 |
| gc 는 유예 24시간 안의 바이트를 지우지 않는다 | T6 | `test_gc_grace` | r3 부록 B T6 · E-14 |
| 첨부 행 삭제와 stored_file 행 삭제가 한 트랜잭션 | T6 | `test_gc_owner_delete_cascade` | r3 부록 B T6 · E-14 |
| html 패키지 열기 501, 교체 뒤 옛 `href` 404 | T6 | `test_attachment_` | r3 §5.2 T6 · ADR-003 |
| 강사 화면 읽기(홈·포털 미리 보기·초대코드·안내문·명단)는 배정 강의만, 남의 강의 403, 포털 미리 보기는 수강생 포털과 같고 명단에 이메일이 없다 | T6 | `test_instructor_view_` | T6 계획 결정 xiii·xiv·xviii·xxi |
| 기록 상태 none → done → ok, 확인 뒤 강사 수정 → done, 관리자 저장 → ok, 진행 내용 없으면 422, 포털에 기록 칸 없음 | T7 | `test_record_` | r3 부록 A4 · §5.2 T7 · T7 계획 결정 iii |
| 예정 차시 사진 409, 남의 사진 삭제 403 | T7 | `test_photo_` | r3 부록 B T7 · T7 계획 결정 viii |
| 1인 1회, 응답 뒤 문항 잠금, 강의당 열린 설문 1개 | T8 | `test_survey_` | r3 부록 A4 · 부록 B T8 · T8 계획 결정 ix·xix |
| 열린 설문 동시성 | T8 | `test_concurrent_survey_deploy_one_open` | r3 §5.2 T8 · E-11 · T8 계획 결정 xix·xxii |
| I7 결과에 개인 키·제출 시각 없음, 최소 응답 수 임계 적용 | T8 | `test_no_personal_keys_i7` | r3 §4 · 부록 D · E-14 · T8 계획 결정 xii |
| A5 결과에 개인 키·제출 시각 없음 | T8 | `test_no_personal_keys_a5` | r3 §4 · 부록 B T8 · E-14 |
| 진단 점수는 시안 `calc` 와 같은 값(golden) | T9a | `test_golden_score_` | r3 부록 A4 · 부록 D · E-12 · T9a 계획 결정 v·xv |
| 진단 링크: 회사당 open 1, 제출 즉시 닫힘, 만료·회수·제출 링크는 이유 코드만(410), 제출 응답에 점수 없음 | T9a | `test_diag_link_` | r3 부록 A4 · §5.2 T9a · 부록 B T9a · T9a 계획 결정 vi·xxv |
| 확정 전 회차로 개설 ③ 409 | T9a | `test_open_course_diagnosis_` | r3 부록 B T9a · T9a 계획 결정 vii |
| 회사: 회사명·담당자 필수, 부서 ≤ 20, 활성 연결 강의 있으면 삭제 409(보관 강의 연결은 SET NULL), 삭제가 회차·링크를 같이 지움 | T9a | `test_company_` | 요구정의서 DIA-001 · r3 309 · T9a 계획 결정 iii |
| 진단 회차: 회사당 회차 번호 유일, 17지표 전부 답해야 확정, 그 전엔 level null, 링크 회차의 제출일 잠금, 확정 뒤 PATCH·reco·재확정·삭제 409, 리포트 영역 200×4·총 800·L1~L5·직전 완료 회차와 증감, 권장 구성은 부서 → 직무군 매핑 + 카탈로그 후보 ≤ 3 | T9a | `test_diagnosis_` | 요구정의서 DIA-004~007 · 6.4 · 기획안 :832·:834·:844 · T9a 계획 결정 iv·v·viii |
| 교육 문의: honeypot 응답 동일 + 0행, 1분 재제출 200 같은 영수증, Company 0행, 확인 메일에 내용 없음, 수신 주소 미설정 501 | T9b | `test_inquiry_` | r3 §5.2 T9b · 부록 B T9b |




---

# Resources

- 승인된 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §0 · §2 · §3 · §4 · §5.2 · §6 · 부록 A4 · B(시험 세부) · C · D · E7 · 변경 기록 N4~N13. r1 `.omc/plans/2026-10-21-classfit-phase1.md` B0~B2. 저장소 루트 기준 경로이고, `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 코드 줄 번호는 r3 부록 D 의 인용(뼈대 e80387f 기준)이고, 2026-10-22 에 가지 T0b-sdlc-okf 에서 다시 확인했다.
