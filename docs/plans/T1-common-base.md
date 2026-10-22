---
type: Task Plan
title: "Plan: T1 common-base"
description: 관리자 로그인·auth_session·auth_attempt·outbox·issue_email_code()·stored_file·파일 Bearer 전달·flush_or_conflict·Today·커서·관리 명령 3·import-linter 계약 ② 와 마이그레이션 0002 를 까는 공통 바닥 태스크 계획
date: 2026-10-22
tags: [plan, task, t1, auth, files, classfit]
Archives: false
URL: ""
---

# Plan: T1 common-base (from plan.md#T1, 2026-10-22)

- 근거: intent [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · spec 절 [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) §1 수명 · §2 인증 갈래 · §3 외부 포트 · §4 0002 행 · §5 규칙 1~5·7~10·12~15·18~20 · 부록 A T1 9행 · 태스크 [`plan.md#T1`](../process/plan.md) 3절 T1 행. 그 밖에 [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md) · [`docs/process/adr/ADR-003-external-ports.md`](../process/adr/ADR-003-external-ports.md) · r3 §5.2 T1 행 · §6 · 부록 B T1 · D · J(T1 · R5).
- 승인: 
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T1" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.
- 가지 `T1-common-base` 는 T0b 머리에서 딴다(겹침 허용, plan.md 1절 9 · r3 §3 D2). `git merge-base T0b-sdlc-okf master` = `181006e510f630b914ca7af69c2a7bd02e9955a8`(master `merge: T0a sdlc-bootstrap`).
- 표기: 〔정함〕은 Design 에 없는 이름·값을 이 계획이 정했다는 뜻이다. 표시가 없는 표·칸·함수·경로 이름은 Design 4·5절, ADR-002·003, r3 부록 B·D 의 것이다.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T0a 병합 · ADR-002·003 병합 | 됐다. master `181006e` | plan.md T1 행 · r3 §1 |
| `argon2-cffi` 추가 | **이 계획의 approve 커밋이 그 승인이다**(T0b 의 pyyaml 전례). 해시는 argon2id(argon2-cffi `PasswordHasher` 기본형) | r3 §1 · feature intent 열린 질문 3 |
| 의존성 추가 절차 | approve 커밋 뒤에만 `requirements.in` 을 고친다 → `make lock` → `make install`. deny-deps 훅은 금지 목록만 막아 argon2-cffi 행은 통과한다. 그래서 순서는 기계가 아니라 이 계획이 지킨다 | CLAUDE.md Rules · r3 부록 E8 |
| 그 밖의 새 의존성 | 없다. python-multipart 는 T2b 다 | plan.md T2b 행 |
| T0b | 겹쳐 진행한다. T1 병합은 T0b 병합 뒤다(위험 1행) | plan.md 1절 9 |
| 로컬 DB | brew PG17 `classfit_dev`·`classfit_test`(`make db-create`). 시험 DB 이름은 `_test` 로 끝나야 한다(tests/conftest.py:43). `.env` 는 읽지 않는다 | CLAUDE.md Commands |
| R5 | `FILE_STORE_ROOT` 예시는 `var.nosync/files` 이고 `.gitignore` 에 `var.nosync/` 가 있다 | r3 부록 J T1 · 변경 기록 R5 |
| 인증 코드 해시를 둘 표 | **승인자가 고른다.** Design 은 해시 저장을 T1 에 두고(5절 8 · 부록 A `test_email_code_` "미리 보기는 해시를 저장하지 않는다"), 그 표 `email_verification` 은 0005(T3)에 둔다. **(a) 기본:** 0002 에 `email_verification`(id · code_hash · tries)만 앞당기고, 강사 연결 칸은 T3 가 0005 에서 더한다. Design 4절 0002·0005 행을 같은 커밋에서 고친다. **(b):** 앞당기지 않는다. T1 시험은 "미리 보기는 롤백, sent_at NULL" 까지만 재고, 해시 저장 시험은 T3 로 옮겨 부록 A T1 행 문구를 고친다. approve 커밋 본문에 `(b)` 가 없으면 (a) 다 | Design 4절 0005 · 5절 8 · r3 부록 B T1 |
| 기본값으로 진행하는 결정 | 승인자가 approve 전에 바꾸라고 하지 않으면 이대로 간다. **(i)** 잠금 판정 = 최근 15분 실패 ≥ 10. 잠긴 요청도 실패 행을 남기고 429 를 준다〔정함〕(위험 표 "잠금 시간 해석" 행). **(ii)** 수명 값은 설정 기본값(Design 1절 값)을 가져서 `Settings.missing()` 대상은 `FILE_STORE_ROOT` 하나다(ADR-002 결정 5). Design 5절 20 의 "1절 수명 값들은 없으면 501" 과 달라지므로 문서 단계에서 5절 20 을 고친다. **(iii)** (b) 를 고르면 T3 전까지 `outbox_preview --apply` 는 kind `email_code` 행에서 exit 3 "저장할 표 없음(T3)" 으로 멈추고 아무것도 커밋하지 않는다. 미리 보기는 (a)·(b) 가 같다 | 위험 표 · Design 1절·5절 20 · ADR-002 |

| 칸 | 2026-10-22 에 확인한 값 (방법) |
|---|---|
| 파이썬 · argon2 | `.venv` Python 3.14.7. `import argon2` 는 ModuleNotFoundError. `pip index versions argon2-cffi` 최신 25.1.0. 판은 `make lock` 이 정한다 |
| `.env.example` | 키는 `CLASSFIT_DATABASE_URL`·`CLASSFIT_TEST_DATABASE_URL`·`CLASSFIT_ENABLE_DOCS` 셋(`grep -oE '^[A-Z_]+='`, 값은 읽지 않음) |
| 시간대 | `.venv/bin/python -c 'import zoneinfo; zoneinfo.ZoneInfo("Asia/Seoul")'` 로컬 성공 |
| 뼈대 부품 | `problem()` 은 401 이면 `WWW-Authenticate: Bearer` 를 단다(app/errors.py:88-89). `not_configured` → 501(app/errors.py:33). 계약 픽스처는 연결 하나에 `create_savepoint` 로 묶인다(tests/contracts/conftest.py:45-47). pyproject 계약은 ①·③ 둘(pyproject.toml:62-90) |

## 바뀌는 파일

레인 A, 워커 하나다. 워커를 나누면 이 머리에 소유 파일을 적는다(plan.md 2절).

**워커 소유(계획 42행 — 2단계에서 워커 2명으로 나눔, 사용자 지시 "승인을 몰아서 빠르게" 2026-10-22)**
- worker-a(인증·DB 경로): `requirements.in/.txt` · `.env.example` · `core/config.py` · `core/passwords.py` · `alembic/versions/0002_common_base.py` · `models/{admin,auth,outbox,stored_file,__init__}.py` · `crud/{flush,admin,auth,outbox,stored_file,scope}.py` · `service/auth/**` · `schemas/{auth,admin}.py` · `app/deps.py` · `app/endpoints/{auth,admins}.py` · `app/routers.py` · `tests/fixtures/probe_routes.py` · `tests/contracts/{test_api_auth,test_api_admins,test_api_conflict,test_api_openapi}.py`·`expected_paths.txt` · `tests/integration/{test_db_auth_session,test_db_email_code}.py` · `tests/unit/test_passwords_rules.py`. 시험 DB `classfit_test`.
- worker-b(파일·유틸·관리 명령·경계·문서): `core/{cursor,clock}.py` · `schemas/page.py` · `crud/page.py` · `service/files/**` · `app/endpoints/files.py` · `scripts/{create_admin,file_gc,outbox_preview}.py` · `tests/unit/{test_cursor_rules,test_clock_rules}.py` · `tests/integration/{test_db_page,test_db_admin_commands}.py` · `tests/contracts/test_api_files.py` · `pyproject.toml`(계약 ②) · `docs/process/{plan,spec}.md`·Design·`CLAUDE.md`. 시험 DB `classfit_b_test`(이 태스크에서 새로 만듦, `_test` 접미).
- 공유 파일(`app/routers.py`·`models/__init__.py`·`probe_routes.py`)은 A 만 편집. 리뷰 반영 커밋도 같은 소유로.

**의존성 · 설정**
- `requirements.in` (modify): `argon2-cffi` 한 줄(착수 조건).
- `requirements.txt` (modify): `make lock` 산출물. argon2-cffi 와 그 이행 의존성 행만 늘고 기존 판은 그대로여야 한다.
- `requirements-dev.txt` (modify 없음 기대): `-c requirements.txt` 를 따르므로 바뀌면 diff 를 보고 판 올림이 없는지 본다.
- `.env.example` (modify): `CLASSFIT_FILE_STORE_ROOT=` 키와 예시 주석 `var.nosync/files`(R5). 값은 비운다.
- `src/classfit/core/config.py` (modify): 칸 〔정함〕 `file_store_root: Path | None`(`missing()` 대상) · `file_signing_key: SecretStr | None`(예약, `missing()` 밖, ADR-003 결정 3) · `admin_session_hours = 8` · `learner_session_days = 1`(ADR-002 결정 5) · `login_lock_failures = 10` · `login_lock_minutes = 15` · `file_gc_grace_hours = 24`. 수명 값은 Design 1절 값을 기본값으로 둔다(ADR-002 결정 5 "설정 기본값"). 그래서 T1 의 `missing()` 대상은 `FILE_STORE_ROOT` 하나다. `missing()` 독스트링의 "503" 을 "501" 로 고친다(r3 부록 I-10).

**core**
- `src/classfit/core/passwords.py` (new) 〔정함〕: `hash_password`·`verify_password`·`DUMMY_HASH`. argon2id. 없는 아이디도 같은 대조를 거치게 한다.
- `src/classfit/core/cursor.py` (new) 〔정함〕: `encode_cursor(t, i)`·`decode_cursor(s)` = base64url(`{"t":시각,"i":id}`)(백엔드 안내서 §3.1). 깨진 커서는 `ValueError` 다. 422 로 바꾸는 일은 첫 목록 끝점(T2a)이 한다.
- `src/classfit/core/clock.py` (new) 〔정함〕: `KST = ZoneInfo("Asia/Seoul")` · `today_kst(now)`. `Today` 의 원천이다(Design 5절 15).

**마이그레이션 · models** — models 파일 이름은 〔정함〕이다.
- `alembic/versions/0002_common_base.py` (new, 파일 이름 〔정함〕): 리비전 `0002`, down `0001`. 표 5개(+ (a) 면 6개)를 만들고 역순으로 지운다. 상태·종류 열은 Text 다(Design 5절 12).
- `src/classfit/models/admin.py` (new): `admin_account` = `AdminAccount`〔정함〕. id · login_id U(소문자·앞뒤 공백 제거 〔정함〕) · password_hash〔정함〕 · TimestampMixin.
- `src/classfit/models/auth.py` (new): `auth_session` = `AuthSession`〔정함〕. id · token_hash U · principal_type(CHECK admin·instructor·learner) · principal_id · course_id · expires_at〔정함〕 · revoked_at〔정함〕 · created_at〔정함〕. CHECK `(principal_type = 'learner') = (course_id IS NOT NULL)`(ADR-002 결정 1). FK `course_id→course` 는 0003 이다. `auth_attempt` = `AuthAttempt`〔정함〕. id · kind · subject_hash(= 정규화한 login_id 의 sha256 hex 〔정함〕) · client · at · ok, 색인 (kind, subject_hash, client, at)〔정함〕. kind 는 상태 열이 아니어서 CHECK 를 두지 않는다〔정함〕. T1 의 kind 값은 `admin_login` 하나다. (a) 면 `email_verification` = `EmailVerification`〔정함〕(id · code_hash · tries)도 여기 둔다.
- `src/classfit/models/outbox.py` (new): `mail_outbox` = `MailOutbox`〔정함〕. id · kind · params JSONB · to · sent_at · created_at〔정함〕. `to` 는 SQL 예약어라 원시 SQL 에서는 따옴표로 쓴다.
- `src/classfit/models/stored_file.py` (new): `stored_file` = `StoredFile`〔정함〕. id · key U · sha256(색인 〔정함〕) · owner_kind · owner_id · content_type〔정함〕 · size〔정함〕 · created_at〔정함〕. 다형 참조라 FK 가 없다(Design 4절).
- `src/classfit/models/__init__.py` (modify): 새 표 클래스를 재노출한다.

**schemas** 〔정함〕
- `src/classfit/schemas/auth.py` (new): `AdminLoginIn{login_id, password}` · `TokenOut{access_token, token_type, expires_at}`.
- `src/classfit/schemas/admin.py` (new): `AdminCreateIn{login_id 3~64자, password 12자 이상}` · `AdminOut{id, login_id, created_at}`.
- `src/classfit/schemas/page.py` (new): `Page[T]{items, next_cursor, has_more}`(Design 5절 2).

**crud** — 첫 인자 session, flush 까지(Design 5절 4). `scope.py` 밖의 파일 이름은 〔정함〕이다.
- `src/classfit/crud/flush.py` (new, 파일 이름 〔정함〕): `flush_or_conflict(session, message)`. begin_nested 안에서 flush 하고 `exc.orig.sqlstate == '23505'` 일 때만 `Conflict`, 나머지는 다시 던진다(Design 5절 5).
- `src/classfit/crud/admin.py` (new): 아이디로 찾기 · 넣기(flush_or_conflict).
- `src/classfit/crud/auth.py` (new): 세션 넣기 · 토큰 해시로 유효한 세션 찾기(revoked_at NULL ∧ expires_at > now()) · 폐기 · 시도 넣기 · (subject_hash, client) 의 최근 창 실패 세기 · (a) 면 code_hash 덮기와 tries 0.
- `src/classfit/crud/outbox.py` (new): `enqueue(kind, params, to)` · 안 보낸 행 · `mark_sent`.
- `src/classfit/crud/stored_file.py` (new): 넣기 · key 로 찾기 · 참조 중인 sha256 집합(gc).
- `src/classfit/crud/scope.py` (new): 주체 범위(Design 5절 3). `OWNER_KINDS: dict[str, 판정]`〔정함〕은 T1 에서 비어 있어 모든 종류가 404 다(기본 거절). 종류는 T2b 부터 Design 4절 순서로 등록한다.
- `src/classfit/crud/page.py` (new) 〔정함〕: `keyset_page(stmt, cursor, limit)`. (created_at, id) 키셋, limit+1 행으로 has_more.

**service** — 구성요소 폴더. 서로 import 하지 않는다(계약 ②). 정면 재노출은 두지 않아 stale_patch_guard FACADES 는 그대로다.
- `src/classfit/service/auth/__init__.py` (new): 독스트링만.
- `src/classfit/service/auth/login.py` (new) 〔정함〕: `admin_login()`. 잠김 판정 → 아이디 조회 → 대조(없는 아이디는 `DUMMY_HASH`) → `auth_attempt` 1행(subject_hash 는 models 줄의 정의 〔정함〕) → 성공이면 세션. 결과 값만 돌려주고 예외를 던지지 않는다. 판정 전에는 쓰지 않는다(Design 5절 7 대가).
- `src/classfit/service/auth/sessions.py` (new) 〔정함〕: `Principal(type, id, course_id)` · 새 토큰 `secrets.token_urlsafe(32)`(저장은 sha256 hex) · 인증 · 폐기. 수명은 설정 칸에서 읽는다.
- `src/classfit/service/auth/email_code.py` (new, 파일 이름 〔정함〕): Design 의 `service/auth.issue_email_code` 를 하위 파일로 푼다. 부르는 쪽은 `classfit.service.auth.email_code` 에서 가져온다. `issue_email_code(session, verification_id) -> str` 한 함수(Design 5절 8·13). 6자리 숫자 〔정함〕, 해시 argon2id 〔정함〕, 다시 부르면 이전 해시를 덮는다. 생성 도우미 `_new_code` 는 이 파일 밖에서 부르지 않는다.
- `src/classfit/service/files/__init__.py` · `src/classfit/service/files/store.py` (new, 구성요소·파일 이름 〔정함〕): `store_bytes()`(디스크 배치 `<root>/<sha256 앞 2자>/<sha256>`〔정함〕에 없으면 쓰고 있으면 mtime 만, 행은 호출자 트랜잭션, Design 5절 9) · `path_for(sha256)`(64자 hex 만 받는다) · `href_for(key)` = `/v1/files/{key}`(Design 5절 10) · `gc_candidates(root, referenced, grace)`.

**app**
- `src/classfit/app/deps.py` (modify): `bearer_principal`〔정함〕(헤더 없음·모양 틀림·없는 토큰·폐기·만료 → `unauthorized()` 401) · `AdminCaller`〔정함〕(관리자 아니면 `forbidden()` 403) · `Today`(Design 5절 15. 시험은 `dependency_overrides` 로 주입).
- `src/classfit/app/endpoints/auth.py` (new) 〔정함〕: `POST /v1/auth/admin/login`. 200 TokenOut · 실패 401 · 잠김 429〔정함〕. 실패·잠김은 `problem()` 을 **반환**해서 `db()` 가 auth_attempt 를 커밋한다(Design 5절 7). `POST /v1/auth/logout` 204.
- `src/classfit/app/endpoints/admins.py` (new) 〔정함〕: `POST /v1/admin/admins`. AdminCaller, 201, 같은 아이디 409, `insert_audit` 1행(`admin.create`, target `admin_account`·id 글자)〔정함〕.
- `src/classfit/app/endpoints/files.py` (new) 〔정함〕: `GET /v1/files/{key}`. 401 → 501(`missing("file_store_root")`) → 404(행 없음·미등록 종류) → 403(범위) → 200 바이트(`Cache-Control: private, no-store`〔정함〕). 설정은 `request.app.state.settings` 에서 읽는다. 501 이 404 보다 앞이므로 시험은 `app.state.settings` 를 `file_store_root=tmp_path` 인 Settings 로 바꿔 넣고 404·403·200(증명 4번 포함)을 잰다. 501 시험만 그 칸을 비운 채 둔다.
- `src/classfit/app/routers.py` (modify): ROUTERS 에 셋을 더한다.

**관리 명령** — `python -m scripts.<이름>`(Design 2절 · r3 부록 B T1). 미리 보기가 기본이고 `--apply` 일 때만 커밋한다. 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절, 결과 JSON 은 stdout, 안내는 stderr(백엔드 안내서 §3.4). 계약 ① 이 exhaustive 라 패키지 안에 `cli/` 를 만들지 않는다(Design 5절 14). 셋 다 `run(argv, session_factory, …) -> int`〔정함〕를 둬서 시험이 시험 연결을 넘긴다.
- `scripts/create_admin.py` (new): `--login-id` 만 받는다. 비밀번호는 getpass 로 두 번 받고 argv 칸이 없다. 같은 아이디는 3. `--apply` 면 audit actor `system`.
- `scripts/file_gc.py` (new): 참조 행 0 ∧ mtime 이 `file_gc_grace_hours` 지난 바이트만 지운다. `FILE_STORE_ROOT` 가 없으면 3.
- `scripts/outbox_preview.py` (new): 안 보낸 행마다 본문을 찍는다. kind `email_code` 는 `issue_email_code()` 를 부른다. 미리 보기는 "무효 코드(미리 보기)" 를 찍고 롤백한다. `--apply` 는 해시를 저장하고 sent_at 을 채운다. 모르는 kind 는 3. (b) 면 T3 전까지 `--apply` 는 kind `email_code` 에서 exit 3 이다(착수 조건 (iii)).

**경계**
- `pyproject.toml` (modify): 계약 ② `2. service 구성요소는 서로 모른다` 〔이름 정함〕 = `type = "independence"`, 모듈 `classfit.service.auth`·`classfit.service.files`. 위아래 계약(`rules` 최하위)으로 바꾸는 일은 rules 가 생기는 T2a 다(Design 5절 14). ①·③ 은 그대로다.

**시험** — Design 부록 A T1 9행 전부. 파일 이름은 Design 5절 18 규약, 함수 이름은 접두 뒤를 〔정함〕.
- `tests/contracts/test_api_auth.py` (new): `test_admin_login_wrong_password_and_unknown_id_same_401` · `test_admin_login_ok_returns_opaque_token`(DB 에 평문 토큰 없음) · `test_admin_login_revoked_token_401` · `test_admin_login_expired_token_401` · `test_auth_attempt_row_survives_401`(auth_attempt 1행, admin_account·auth_session 행 수 그대로) · `test_auth_lockout_same_client_429_after_10_failures` · `test_auth_lockout_other_client_not_locked`(httpx `ASGITransport(client=("192.0.2.10", …))` 와 `192.0.2.11`).
- `tests/contracts/test_api_admins.py` (new, 부록 A 밖): `test_admin_create_ok_201`(audit 1행) · `test_admin_create_non_admin_403` · `test_admin_create_invalid_422`.
- `tests/contracts/test_api_conflict.py` (new): `test_flush_or_conflict_unique_is_409`(같은 아이디로 `POST /v1/admin/admins`) · `test_flush_or_conflict_check_is_500`(probe, client_noraise, 행 0) · `test_outbox_rolled_back_on_409`(probe, mail_outbox 0행).
- `tests/contracts/test_api_files.py` (new): `test_files_requires_bearer_401` · `test_files_store_root_unset_501` · `test_files_unregistered_owner_kind_404` · `test_files_unknown_key_404` · `test_files_out_of_scope_403` · `test_files_ok_without_signing_key_200`. 시험 전용 종류는 `monkeypatch.setitem(classfit.crud.scope.OWNER_KINDS, "probe", …)` 로 넣는다(정의 모듈이라 guard 대상 밖).
- `tests/contracts/test_api_openapi.py` (new, r3 E-13 의 파일): `test_openapi_paths_match_expected_without_probe`. probe 를 붙이지 않은 새 `create_app(Settings())` 의 paths 집합이 expected_paths.txt 와 같다.
- `tests/contracts/expected_paths.txt` (new): `/v1/admin/admins` · `/v1/auth/admin/login` · `/v1/auth/logout` · `/v1/files/{key}` · `/v1/health` 다섯 줄(Design 1절 API 정본).
- `tests/fixtures/probe_routes.py` (modify): probe 2개, 경로 〔정함〕. `POST /v1/_probe/check-violation` 은 learner 세션을 course_id 없이 넣고 flush_or_conflict 한다. `POST /v1/_probe/outbox-then-conflict` 는 outbox 1행 뒤 같은 아이디 관리자를 넣는다. ROUTERS 밖 그대로다(Design 5절 1).
- `tests/integration/test_db_auth_session.py` (new): `test_auth_session_learner_without_course_violates_check` · `test_auth_session_admin_with_course_violates_check`(IntegrityError, sqlstate 23514).
- `tests/integration/test_db_email_code.py` (new): `test_email_code_generated_only_in_issue_email_code`(src 에서 `_new_code` 를 부르는 파일이 하나) · `test_email_code_preview_stores_no_hash` · `test_email_code_apply_stores_hash_and_sent_at` · `test_email_code_reissue_overwrites_hash`. 미리 보기·apply 두 시험은 `scripts.outbox_preview.run`(미리 보기, `["--apply"]`)을 거친다. 재발급 시험은 `issue_email_code()` 를 직접 두 번 부른다(r3 부록 D "시험은 같은 함수를 직접 부른다"). (b) 면 apply·재발급 둘은 T3 로 간다.
- `tests/integration/test_db_admin_commands.py` (new, 부록 A 밖): `test_create_admin_preview_writes_nothing` · `test_create_admin_apply_writes_one_row` · `test_create_admin_password_not_in_argv`(`--password` → exit 2) · `test_file_gc_preview_deletes_nothing` · `test_file_gc_apply_deletes_only_unreferenced_old_bytes`(`os.utime` 로 mtime 을 25시간 전으로).
- `tests/integration/test_db_page.py` · `tests/unit/test_cursor_rules.py` · `tests/unit/test_clock_rules.py` · `tests/unit/test_passwords_rules.py` (new, 부록 A 밖): `test_keyset_page_has_more_and_next_cursor` · `test_cursor_roundtrip` · `test_cursor_tampered_raises` · `test_today_kst_boundary_utc_15`(UTC 14:59 ↔ 15:00) · `test_password_hash_argon2id_roundtrip`(`$argon2id$` 접두).

**문서**
- `docs/plans/T1-common-base.md` (new, 뒤에 modify): 이 계획. 리뷰와 "계획과 다르게 한 것" 을 채운다.
- [`docs/process/plan.md`](../process/plan.md) (modify): T1 행의 계획 파일 칸을 이 파일로, 상태를 "진행 중. 가지 T1-common-base, 승인됨" 으로.
- [`docs/process/spec.md`](../process/spec.md) (modify): 2절 2행 "예정: T1 + `test_openapi_`" → `tests/contracts/test_api_openapi.py`, 6행 "예정: T1 + `test_auth_session_`" → `tests/integration/test_db_auth_session.py`. 1절 plan.md 행의 상태 칸.
- [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) (modify): 4절 0002·0005 행((a) 일 때) · 5절 14 에 T1 계약 ② 모양 한 줄 · 5절 20 수정(수명 값은 기본값을 가진다, 착수 조건 (ii)). 부록 A 는 접두가 그대로라 고치지 않는다((b) 면 T1 `test_email_code_` 행 문구).
- `CLAUDE.md` (modify): Rules 경계 줄의 "② 는 T1 에서 더한다" 를 ② 설명으로, Commands 에 관리 명령 3 한 줄.
- docs 목차(`okf index` 가 고친다).

바꾸지 않는 것: `alembic.ini`(사용자 미커밋 변경) · `.env` · `0001` · 기존 시험(probe_routes 만 더한다) · `tests/conftest.py` · `tests/contracts/conftest.py` · `.claude/**` · `Makefile` · `scripts/` 의 셸 스크립트 · templates · ADR · 미추적 `기획/`·`시안/`.

## 작업 순서

커밋은 묶음마다 파일을 지정하고 메시지는 `-F` 파일로 넘긴다. `git add -A`·`git add .`·`git commit -a` 는 쓰지 않는다. 단계마다 관문이 녹색이어야 다음으로 간다.

1. 리드: 가지 `T1-common-base` 를 T0b 머리에서 따고 이 파일과 okf index 가 고친 [`docs/index.md`](../index.md) · [`docs/plans/index.md`](index.md) 를 파일 지정해 `plan: T1 common-base` 로 커밋한다. 트레일러는 없다. [`docs/plans/README.md`](README.md) 의 "이 폴더의 계획 파일만" 문구는 승인자 판단 뒤 맞춘다.
2. 승인자: `approve: T1` 빈 커밋. 이것이 argon2-cffi 승인이고, 본문에 `(b)` 가 있으면 착수 조건의 (b) 다. 그 전에는 아래를 시작하지 않는다.
3. 의존성: `requirements.in` → `make lock` → `make install`. 관문: `.venv/bin/python -c 'from argon2 import PasswordHasher; print(PasswordHasher().hash("x")[:10])'` → `$argon2id$` · `git diff requirements.txt | grep -E '^-[a-z]'` 빈 출력 · `git diff --stat requirements-dev.txt` 빈 출력. 커밋 `T1: argon2-cffi 의존성`.
4. 마이그레이션 0002 → models. 관문: `.venv/bin/alembic heads` → `0002 (head)` · `make migrate` 뒤 `.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/alembic check` → `No new upgrade operations detected.` · `.venv/bin/pytest tests/integration/test_db_auth_session.py -q` → `2 passed`. `alembic check` 는 CHECK 제약을 비교하지 않으므로(백엔드 안내서 §7-12) CHECK 는 이 시험이 잰다. 커밋 `T1: 0002 마이그레이션·모델`.
5. core → crud → service, 단위·통합 시험과 같이. 관문: `.venv/bin/pytest tests/unit tests/integration -q` failed·error 0. 커밋 `T1: core·crud·service — 인증·outbox·파일·flush_or_conflict·커서·Today`.
6. schemas → deps → endpoints → routers → probe → expected_paths → 계약 시험. 관문: `.venv/bin/pytest tests/contracts -q` failed·error 0, 증명 표 7항목 녹색. 커밋 `T1: 끝점·deps·계약 시험`.
7. 관리 명령 3 + 시험. 관문: `.venv/bin/pytest tests/integration/test_db_admin_commands.py -q` → `5 passed`. dev 에서 `.venv/bin/python -m scripts.create_admin --login-id admin-a` 미리 보기가 JSON 을 찍고 `/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -Atc 'select count(*) from admin_account'` 가 0 이다. 커밋 `T1: 관리 명령 create_admin·file_gc·outbox_preview`.
8. 계약 ②. 관문: `make lint-imports` → `Contracts: 3 kept, 0 broken.`. 커밋 `T1: import-linter 계약 ②`.
9. 문서(plan.md · spec.md · Design · CLAUDE.md). 이어서 `okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크의 앞뒤 문장을 읽는다 → `okf index --apply` → `okf check --strict` → `위반 0건 — 통과`. 관문: `make okf` → `OKF guard OK`. 커밋 `T1: 문서 — plan·spec·Design·CLAUDE.md`(pre-commit guard 가 돈다).
10. `make verify`(파이프 없이) exit 0. 이어서 "증명" 의 명령 · 이웃 흐름 3개 · 대조 실험 4개를 돌리고 기록 칸에 적는다.
11. 다른 세션의 reviewer 가 "리뷰" 절을 쓰고 Important 0 까지 고친다. DB 쓰기·권한 태스크라 `verifier` 서브에이전트가 "증명" 을 다시 돌린다(CLAUDE.md 검증 표).
12. T0b 병합 뒤 필요하면 `bash scripts/sync_task.sh` 로 master 를 들인다. `bash scripts/check_task_order.sh` → `task order: OK`. 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T1-common-base`.

## 위험

| 위험 | 알아채는 법 | 완화 (출처) |
|---|---|---|
| 가지가 T0b 머리에서 나와 T0b 병합 전에는 `check_task_order` 가 T0b 커밋을 규약 밖으로 보고한다(가지 첫 커밋이 `plan: T1 common-base` 가 아님 등). merge_task ③ 도 같은 이유로 거절한다 | `bash scripts/check_task_order.sh` | 예상된 상태다. T0b 가 병합되면 master..가지에 T1 커밋만 남아 깨끗해진다. 그래서 T1 병합은 T0b 병합 뒤다. T0b 병합 뒤 `sync_task.sh` 로 master 를 들인다. 병합 전에는 들일 길이 없다(`sync_task.sh` 는 master 만 병합하고, 에이전트의 merge·cherry-pick 은 deny 다)(plan.md 1절 6·9, r3 §3 D2) |
| T0b 도 `pyproject.toml`·`CLAUDE.md`·`docs/process/{plan,spec}.md` 를 고친다 | sync 병합 충돌 · `git diff` | 그 파일 변경은 작업 순서 8·9 에 몰아 두고, T0b 가 아직 열려 있으면 T0b 병합과 sync 뒤에 한다 |
| 실패 시도 행이 롤백된다. 실패를 `raise unauthorized()` 로 바꾸면 `db()` 가 롤백한다. 별도 세션으로 쓰면 하네스(연결 하나 + savepoint)에서 요청 롤백과 함께 지워진다 | `test_auth_attempt_row_survives_401` · 대조 실험 1 | 같은 요청 트랜잭션에 쓰고 `problem()` 을 반환한다. 별도 세션·별도 트랜잭션은 쓰지 않는다(Design 5절 7 · r3 N4 · 부록 I-12). 요청 1개 = 트랜잭션 1개가 그대로 선다 |
| 실패 판정 전의 다른 쓰기가 401 과 함께 커밋된다 | 같은 시험이 admin_account·auth_session 행 수를 같이 본다 | 로그인 끝점은 판정 전에 쓰지 않는다(Design 5절 7 대가). REVIEW.md Security 패스 |
| 잠금 키에서 주소가 빠지면 남이 관리자를 묶는다. 프록시 뒤에서는 client.host 가 모두 프록시 주소라 키가 계정 하나로 무너진다 | `test_auth_lockout_other_client_not_locked` · 대조 실험 3 | 키 = (subject_hash, `request.client.host`)(r3 N10). 신뢰 헤더 설정은 운영 단계 결정이다(r3 부록 F) |
| 잠금 시간 해석. Design 1절은 "15분 안 10회 실패면 15분 차단" 이다 | `test_auth_lockout_same_client_429_after_10_failures` | 판정 = 최근 15분 실패 ≥ 10. 잠긴 요청도 실패 행을 남겨서 시도가 멈춘 뒤 15분 안에 풀린다. 두 15분을 칸 하나(`login_lock_minutes`)로 둔다〔정함〕 |
| 없는 아이디와 틀린 비밀번호가 응답이나 시간으로 갈린다 | `test_admin_login_wrong_password_and_unknown_id_same_401`(상태·헤더·본문 같음) | 없는 아이디도 `DUMMY_HASH` 로 argon2 대조를 한다. 시간 차이는 시험하지 않고 리뷰가 본다 |
| 23505 밖의 무결성 위반이 409 로 숨는다 | `test_flush_or_conflict_check_is_500` · 대조 실험 2 | sqlstate 비교는 `flush_or_conflict` 한 곳이다(r3 N5). begin_nested 라 바깥 요청 트랜잭션은 살고, 409 뒤에는 `db()` 가 전부 롤백한다 |
| 409 로 끝난 요청의 outbox 가 남는다 | `test_outbox_rolled_back_on_409` | outbox 는 같은 요청 트랜잭션에 넣는다(Design 3절) |
| 토큰 평문이 DB 에 남는다 | `test_admin_login_ok_returns_opaque_token` | sha256 hex 만 저장한다(Design 2절) |
| 새 owner_kind 가 범위 판정 없이 열린다. key 가 경로로 쓰여 저장소 루트를 벗어난다 | `test_files_unregistered_owner_kind_404` · `test_files_unknown_key_404` | 등록부 기본 거절(빈 dict). 디스크 경로는 행의 sha256(64자 hex 검사)로만 만든다(ADR-003 결정 1·4) |
| 행 커밋 전 바이트를 gc 가 지운다 | `test_file_gc_apply_deletes_only_unreferenced_old_bytes` · T6 `test_gc_grace` | 참조 0 ∧ mtime 24시간, 업로드는 mtime 갱신(Design 5절 9 · r3 N6) |
| 파일 루트가 iCloud 폴더나 추적 경로에 생긴다 | `git check-ignore -q var.nosync/files/x && echo ignored` | 예시는 `var.nosync/files`(gitignore). 저장소 밖이면 iCloud 폴더 밖에 둔다(r3 부록 J T1) |
| 시험이 개발 DB 를 지운다(세션마다 downgrade base) | tests/conftest.py:43 의 `_test` 가드 메시지 | 시험 URL 은 `_test` 로 끝나야 한다. 관리 명령 시험은 Settings 의 DB 주소가 아니라 시험 연결에 묶은 session_factory 를 받는다 |
| `make lock` 이 기존 판을 바꾸거나 argon2-cffi 가 깔리지 않는다. 2026-10-22 로컬 `pip download`(설치 안 함): Python 3.14.7 arm64 에 argon2-cffi 25.1.0 · argon2-cffi-bindings 26.1.0(cp310-abi3) · cffi 2.1.1(cp314) 휠 해결. Linux CI 는 작업 순서 3 관문이 잰다 | 작업 순서 3 관문 · CI test 잡 | 멈추고 보고한다. 다른 해시 라이브러리로 바꾸거나 판을 올리지 않는다(승인 범위 밖) |
| CI 러너에 시간대 자료가 없으면 `ZoneInfo("Asia/Seoul")` 가 실패한다 | CI test 잡의 `test_today_kst_boundary_utc_15` | ubuntu 러너의 시스템 tzdata 를 쓴다. 없으면 `tzdata` 패키지는 새 승인 거리로 보고한다 |
| iCloud dataless venv 가 EDEADLK 를 낸다 | `Resource deadlock avoided` | 재시도하고, verifier 는 스크래치 venv 로 잰다(T0a "계획과 다르게 한 것" 10) |
| gc 의 mtime 재확인~unlink 와 업로드의 `is_file`→`utime` 사이 짧은 경쟁 창에서 행은 있는데 바이트가 없는 상태가 생길 수 있다(reviewer nit 4) | `test_files_missing_bytes_500`(응답·로그에 경로 없음) | 끝점은 `is_file()` 을 먼저 보고 sha256 앞 12자만 로그 + problem 500. 창 자체는 T6 gc 보강(유예·`.tmp-*`)에서 다시 본다 |

## 증명

r3 §6 의 T1 몫과 plan.md 증명 요약 7항목이다. E-8 은 T1 시점 값이다.

```bash
bash scripts/check_task_order.sh                    # E-1 T0b 병합 뒤 → "task order: OK"(병합 전에는 T0b 커밋을 위반으로 찍는다, 위험 1행)
make verify                                         # E-3 exit 0 · "gate: OK" · "All checks passed!" · "Contracts: 3 kept, 0 broken." · "passed"(failed·error·skipped 0) · 마지막 줄 "OKF guard OK"
.venv/bin/lint-imports                              # "Contracts: 3 kept, 0 broken."
.venv/bin/alembic heads                             # E-8 T1 시점 → "0002 (head)"
.venv/bin/pytest tests/contracts/test_api_openapi.py -q                 # E-13 → "1 passed"
for n in test_admin_login_ test_auth_attempt_ test_auth_lockout_ test_auth_session_ test_files_ test_flush_or_conflict_ test_outbox_ test_email_code_ test_openapi_; do grep -rqE "def ${n}[A-Za-z0-9_]*\(" tests || echo "없음 $n"; done; echo table-ok   # 병합 전 check_docs ④ 근사 → "table-ok" 한 줄만
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh                  # 병합 뒤 ④ 대상에 T1 9행 → "docs check: OK"
```

| # | 관문 (plan.md T1 행) | 명령 `.venv/bin/pytest <노드> -q` | 기대 |
|---|---|---|---|
| 1 | 401 + WWW-Authenticate | `tests/contracts/test_api_auth.py::test_admin_login_wrong_password_and_unknown_id_same_401` | `1 passed`. 두 응답 모두 401 · `WWW-Authenticate: Bearer` · 같은 problem 본문 |
| 2 | 실패 시도는 401 응답 뒤에도 남음 | `tests/contracts/test_api_auth.py::test_auth_attempt_row_survives_401` | `1 passed`. 응답 뒤 auth_attempt `ok = false` 1행 |
| 3 | 다른 클라이언트 주소는 잠금과 무관 | `tests/contracts/test_api_auth.py::test_auth_lockout_other_client_not_locked` | `1 passed`. 192.0.2.10 이 10회 실패해도 192.0.2.11 은 200 |
| 4 | 미등록 owner_kind 404 | `tests/contracts/test_api_files.py::test_files_unregistered_owner_kind_404` | `1 passed` |
| 5 | 유일 위반 409 | `tests/contracts/test_api_conflict.py::test_flush_or_conflict_unique_is_409` | `1 passed`. type `/problems/conflict` |
| 6 | CHECK 위반 500 | `tests/contracts/test_api_conflict.py::test_flush_or_conflict_check_is_500` | `1 passed`. problem+json 500, 내부 메시지 없음 |
| 7 | 409 요청의 outbox 0행 | `tests/contracts/test_api_conflict.py::test_outbox_rolled_back_on_409` | `1 passed`. mail_outbox 0행 |

**이웃 흐름 — 실제 호출**(CLAUDE.md "바뀐 동작 1개와 이웃 흐름 2개"). dev DB 에서 `make migrate` 와 `make run` 뒤에 한다. 마지막 줄이 이 흐름이 남긴 dev 행(관리자 2 · 세션 · 시도 · audit)을 한 트랜잭션으로 지운다. 안 지우면 다시 돌릴 때 create_admin 이 같은 아이디로 exit 3 이다.

```bash
.venv/bin/python -m scripts.create_admin --login-id admin-a --apply    # 비밀번호는 getpass 두 번(argv 에 없음)
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/admin/login -H 'content-type: application/json' -d '{"login_id":"admin-a","password":"<입력한 값>"}' | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/v1/admin/admins -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"login_id":"admin-b","password":"<12자 이상>"}'   # 바뀐 동작 → 201
curl -s -X POST localhost:8000/v1/admin/admins -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"login_id":"admin-c"}'   # 422 → problem+json, violations[].loc 에 "password"
/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -c "insert into auth_session (token_hash, principal_type, principal_id, course_id, expires_at) values (encode(sha256('probe-learner'::bytea), 'hex'), 'learner', 1, 1, now() + interval '1 hour')"
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/v1/admin/admins -H 'Authorization: Bearer probe-learner' -H 'content-type: application/json' -d '{"login_id":"admin-d","password":"<12자 이상>"}'   # 403
/opt/homebrew/opt/postgresql@17/bin/psql -d classfit_dev -v ON_ERROR_STOP=1 -c "delete from audit_log where action = 'admin.create' and target_type = 'admin_account' and target_id in (select id::text from admin_account where login_id in ('admin-a', 'admin-b')); delete from auth_session where token_hash = encode(sha256('probe-learner'::bytea), 'hex') or (principal_type = 'admin' and principal_id in (select id from admin_account where login_id in ('admin-a', 'admin-b'))); delete from auth_attempt where kind = 'admin_login' and subject_hash in (encode(sha256('admin-a'::bytea), 'hex'), encode(sha256('admin-b'::bytea), 'hex')); delete from admin_account where login_id in ('admin-a', 'admin-b')"   # 정리. audit 의 target 은 (admin_account, id 글자)〔정함〕. 한 -c 의 여러 문장은 한 트랜잭션이다
```

**대조 실험**(커밋 뒤 임시 clone 에서만, CLAUDE.md). `git clone -q --no-hardlinks . "$tmp/c"` 사본을 고치고, 원본 `.venv` 와 `PYTHONPATH=<사본>/src` 로 그 시험만 돌려 빨간지 본다. 사본에는 `.env` 가 없으니 `CLASSFIT_TEST_DATABASE_URL` 을 셸 환경 변수로 넘긴다(tests/conftest.py:36 이 셸 환경을 먼저 읽는다). 끝나면 사본을 지운다.
1. 로그인 실패의 `return problem(…)` → `raise unauthorized()`: `test_auth_attempt_row_survives_401` 이 빨개진다(행 0).
2. `flush_or_conflict` 의 sqlstate 비교를 빼고 모든 IntegrityError 를 Conflict 로: `test_flush_or_conflict_check_is_500` 이 빨개진다(409).
3. 잠금 세기에서 client 조건을 뺀다: `test_auth_lockout_other_client_not_locked` 가 빨개진다(429).
4. 0002 의 auth_session CHECK 를 지운다: `test_auth_session_*` 2건이 빨개진다.

| 기록 칸 | 값 |
|---|---|
| 착수 조건 (a)/(b) 선택 (approve 커밋 해시) | `08c6506 approve: T1`(2026-10-22, 본문에 (b) 없음) → **(a)**: `email_verification` 을 0002 에. argon2-cffi 승인 겸함 |
| `make verify` 끝 20줄 | 리뷰 반영 뒤 최종(리드, 머리 584bd65, 2026-10-22): exit 0 · `gate: OK` · `All checks passed!` · `Contracts: 3 kept, 0 broken.` · `76 passed`(failed·error·skipped 0) · 끝줄 `OKF guard OK`. verifier-t1(5688f82) 도 rc 0 · 70 passed · `OKF guard OK` |
| `git diff --stat requirements.txt requirements-dev.txt` · argon2-cffi 판 | requirements.txt 추가 4행(argon2-cffi 25.1.0 · argon2-cffi-bindings 26.1.0 · cffi 2.1.1 · pycparser 3.11), 제거 행 0 · requirements-dev.txt 변경 0 |
| `alembic heads` · dev `alembic check` | `0002 (head)` · `No new upgrade operations detected.`(worker-a 4단계, verifier 재측정 `alembic heads`·dev `alembic current` 둘 다 `0002 (head)`, `alembic check` rc 0) |
| 증명 표 7항목 출력 | 각 노드 `1 passed`(worker-a 6건 + worker-b 4번, verifier 재측정 7개 모두 `1 passed` + openapi `1 passed`). 전체 `pytest tests -q` 리뷰 반영 전 70 → 뒤 76 passed, skip 0 |
| 이웃 흐름 응답 코드(201 · 422 · 403) | verifier-t1 이 dev DB 에 uvicorn 8000 으로 실측(2026-10-22): 로그인 200(token_type bearer, expires_at +8h, access_token 43자) · **바뀐 동작 `POST /v1/admin/admins` 201**(`{"id":5,"login_id":"admin-b",…}`) · password 누락 422 problem+json(`violations[0].loc=["body","password"]`) · 토큰 없음 401 + `www-authenticate: Bearer` · learner 세션 403(`/problems/forbidden`) · 추가: 틀린 비밀번호 401, 같은 아이디 409 `/problems/conflict`. 관리 명령: 미리 보기 0행 · `--apply` 1행 · 같은 아이디 rc 3 · `--password` rc 2. 서버 로그에 토큰·비밀번호 평문 0. 정리 명령 `DELETE 2`×4 rc 0, dev 7표 모두 0행, 8000 LISTEN 없음 |
| 대조 실험 4개(빨개진 시험 이름) | ① `test_auth_attempt_row_survives_401` ② `test_flush_or_conflict_check_is_500` ③ `test_auth_lockout_other_client_not_locked` ④ `test_auth_session_learner_without_course_violates_check`·`test_auth_session_admin_with_course_violates_check`(worker-a 임시 clone, verifier 재측정 verifier-t1 재측정(임시 clone 5688f82, DB classfit_b_test): ① `assert [] == [('admin_login', False)]`(잠금 시험 2개도 함께 빨강 — 실패 행이 안 쌓여서) ② `assert 409 == 500` ③ `assert 429 == 200` ④ 2건 `DID NOT RAISE IntegrityError`. 되돌리면 각각 8·7·8·2 passed, 전체 70 passed. clone 삭제). 계약 ②: service.auth→service.files import 시 `BROKEN`(worker-b) |
| verifier 세션 · 날짜 · 판정 | verifier-t1(다른 세션) · 2026-10-22 · **PASS(증명 충족, 차단 0)**. 토큰: `auth_session.token_hash` 64자 hex = sha256(평문), 평문은 어느 열에도 없음. 인증 코드: 미리 보기 뒤 code_hash·sent_at NULL, `--apply` 뒤 `$argon2id$` 접두 + sent_at, 6자리 평문은 mail_outbox·email_verification 어디에도 없음(stdout 에만). okf 네 관문 label `{'같음': 16}` · link 0 · index 0 · check 위반 0. check_docs ④ `대응표 42행 중 대상 0행`(T1 미병합) |
| `check_task_order`(T0b 병합 전 · 뒤) · 병합 뒤 `check_docs.sh` ④ 대상 행 수 | 병합 전(2026-10-22 00:5x, plan 커밋 직후) `FAIL (위반 9건)`(T0b 커밋이 T1 규약 밖) · T0b 병합 뒤 `task order: OK`(가지 커밋 13개) · check_docs ④: T1 병합(`74f0441`) 뒤 T2a 가지 머리 `a9fe2a8` 에서 `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` 실측(2026-10-22) → `④ 병합된 T: T0a T0b T1 · 대응표 42행 중 대상 9행` · `docs check: OK`(rc 0, ② 외부 정본 5개 sha256 대조 포함) · CI 결과: origin push 미완(2026-10-22) |

## 리뷰

reviewer-t1(다른 세션) · 2026-10-22 · 범위 `git diff master...HEAD` 59 files(+2851/−31) · REVIEW.md 패스 Bugs → Security → Compliance · 판정 **Important 1 / nit 12(표시 5)** → Important 는 이 커밋으로 닫았고, nit 1·3·4·5 와 미표시 2건(미리 보기 코드 마스킹 · hide_parameters)·nit 2 의 잠금 문장은 리뷰 반영 커밋 `3047f7a`(A) · `584bd65`(B) 로 반영했다.

**실행해 본 것**: 구현 커밋 12개 diff 전부(src 30·scripts 3·0002·시험 14 파일 전체 읽음, 커밋마다 트리 대조) · merge-base 226b8b5 와 master b14b180 트리 diff 0 · 구현 커밋에 승인 트레일러 0(Co-Authored-By 만) · 추가 줄 2851 grep(IP 는 192.0.2.10/11, 메일은 example.com, skip·xfail 0) · 시험 삭제 줄 2개는 probe_routes 재배치, 단언 변경 0 · `tests/conftest.py`·`tests/contracts/conftest.py`·`requirements-dev.txt`·`.env`·`alembic.ini` diff 0 · requirements.txt +4행(argon2 계열), 기존 판 변경 0 · 부록 A T1 접두 9개 모두 `def` 있음 · 모델과 0002 의 제약·색인 이름 일치, down 역순 · 정적 확인: psycopg 3.3.6 StrDumper 는 NUL 에 DataError(nit 1), pydantic 2.14 는 외톨이 서로게이트를 422 로 막음, Starlette 1.9.0 FileResponse 는 파일 없으면 RuntimeError(nit 4), FastAPI 0.156.5 scope 규칙은 yield 의존성에만, site-packages 에 최상위 `scripts` 없음(B ⑤ 타당) · pytest·make verify·라이브 DB 는 verifier 몫이라 안 돌림.

**Important**
1. [Important·Compliance] `docs/plans/T1-common-base.md:204-222` · 증명 기록 칸 9행 비어 있음, "계획과 다르게 한 것" 틀 문구 그대로, 워커 2명인데 42행이 요구한 소유 파일 머리 없음 · 근거: `git diff 08c6506..HEAD -- docs/plans/` 0줄. 커밋 분할로 중간 커밋 두 구간이 빨갛다(정적 대조): ⓐ `13b73ab`~`a3b0f05` 는 `test_db_email_code.py` 가 아직 없는 `scripts.outbox_preview` 를 import, ⓑ `6622d1e`~`b4500c3` 는 `expected_paths.txt` 에 `/v1/files/{key}` 가 있는데 ROUTERS 에 files 가 없어 `test_openapi_*` 빨강·`test_files_*` 404 — 125행 "단계마다 관문 녹색" 위반. T0b Important 1 과 같은 발견 두 번째 → CLAUDE.md "Things Claude gets wrong" 후보 · **처리: 반영(이 커밋)** — 기록 칸 9행·편차(A 10·B 8·리드 4)·소유 파일 머리를 채웠다. 중간 커밋의 빨강은 이력을 다시 쓰지 않고 편차로 적었다.

**nit(표시 5)** — 줄 번호는 리뷰 시점(5688f82) 기준

| # | [nit·분류] 파일:줄 | 요지 | 처리 |
|---|---|---|---|
| 1 | [nit·Bugs] `app/endpoints/files.py:31` · `schemas/auth.py:12` · `schemas/admin.py:10-12` · `core/cursor.py:34` | 입력 모양 빈틈이 500: key·login_id 의 NUL 이 psycopg DataError, 커서 i 가 BIGINT 밖이면 ValueError→422 전환을 비킴. 대조 전이라 추측 통로는 아님 | **반영**: key 모양 밖은 같은 404(`584bd65`), login_id 제어 문자 422(`3047f7a`), `decode_cursor` 범위 검사(`584bd65`) |
| 2 | [nit·Security] `service/auth/login.py:49-60` | 실패 세기와 넣기 사이 잠금 없음 → 동시 요청은 9 + 풀 동시 수(15)까지 통과 | **반영 일부**: `pg_advisory_xact_lock(hashtextextended(kind‖subject‖client, 0))` 한 문장(`3047f7a`). 동시성 시험은 Design 5절 18 `test_db_concurrency.py` 가 생기는 T2b 에서 |
| 3 | [nit·Security] `app/endpoints/files.py:22,48-52` | `media_type=row.content_type` 그대로, `nosniff`·`Content-Disposition` 없음. T1 은 업로드가 없어 지금은 쓸 길 없음 | **반영**: `X-Content-Type-Options: nosniff` + 기본 `attachment`(`584bd65`) |
| 4 | [nit·Bugs] `app/endpoints/files.py:48` · `scripts/file_gc.py:62-64` · `service/files/store.py:41-42` | 행은 있는데 바이트가 없으면 Starlette RuntimeError(절대 경로 포함) 500. gc 의 mtime 재확인~unlink 와 업로드의 `is_file`→`utime` 사이 짧은 경쟁 창 | **반영**: 끝점이 `is_file()` 먼저 보고 sha256 앞 12자 로그 + problem 500(`584bd65`). 경쟁 창은 위험 표에 추가 |
| 5 | [nit·Compliance] `docs/process/2026-10-21-phase1-backend-design.md:105` | 5절 1행 `DbSession(app/deps.py:29)` 가 낡음(지금 42행) | **반영**: 줄 번호 없이 이름만(`584bd65`) |

미표시 nit 7건: 미리 보기 본문에 실제 6자리가 찍힘(**반영** `584bd65`, 미리 보기는 마스킹) · 엔진 `hide_parameters` 없음(**반영** `3047f7a`) · `sessions.py:41` expires_at·`crud/outbox.py:32` sent_at 이 앱 시계(비교는 DB now()) → **보류**(T2a 에서 DB 시계로 통일 검토) · 인증 없는 로그인의 argon2 대조에 세마포어 없음(동시 상한 = 풀 15) → **보류** · auth_attempt·auth_session 보존 기한·청소 없음 → **보류**(운영 단계) · `gc_candidates` 가 `.tmp-*` 잔여를 안 지움 → **보류**(T6 gc 보강) · ruff format 재배치로 diff 소음 → 보류.

**verifier-t1 낮은 위험 3건**: 바이트 없는 파일 행(→ nit 4 로 반영) · auth_attempt 정리 잡 없음(보류) · 로그인 시간 차이 시험 없음(DUMMY_HASH 대조에 기댐, 보류).

**편차 판단(reviewer)**: A ①~⑩ 전부 타당(⑤ 의 동시 상한은 미표시 nit) · B ①~⑦ 전부 타당(⑥ 은 diff 소음) · 리드 — 워커 2명 분할·커밋 묶음 분할은 **보류**(소유 머리 없음·중간 커밋 빨강 → 이 커밋으로 머리를 적고 편차로 기록), 시험 DB 분리·sync 생략은 타당.

**요약**: Important 1 → 0(이 커밋) / nit 12(반영 7, 보류 5). 코드에 동작을 깨는 버그·비밀 누출 없음, 시험 약화 없음. 병합 가능 의견(결정은 승인자). 전제였던 기록 칸(verifier `make verify`·증명 7·대조 실험 4)은 채웠다.

## 계획과 다르게 한 것

**리드(팀 구성·순서)**
1. 계획 "레인 A, 워커 하나" 와 달리 워커 2명으로 나눴다(사용자 지시 "승인을 몰아서 빠르게"). 소유: worker-a = 의존성·`core/config.py`·`core/passwords.py`·0002·models·crud(flush·admin·auth·outbox·stored_file·scope)·service/auth·schemas auth/admin·deps·endpoints auth/admins·routers·probe·계약 시험 auth/admins/conflict/openapi·통합 시험 auth_session/email_code. worker-b = `core/{cursor,clock}.py`·schemas page·crud page·service/files·endpoints files·scripts 3·단위 시험 cursor/clock·통합 시험 page/admin_commands·계약 시험 files·pyproject 계약 ②·문서. 공유 파일(routers·models/__init__·probe_routes)은 A 만 편집. 시험 DB 를 분리했다(B 는 새로 만든 `classfit_b_test`) — 두 pytest 세션의 세션 픽스처(downgrade base)가 서로 지우지 않게.
2. T0b 병합 뒤 `sync_task.sh` 를 하지 않았다. T1 가지가 T0b 머리(226b8b5)에서 났고 master `b14b180` 의 트리가 그와 같아 들일 변경이 0 이다. 병합은 3-way(merge-base 226b8b5)로 그대로 된다.
3. 커밋 묶음이 계획 작업 순서와 다르다: 5단계가 A 의 `13b73ab`(core·crud·service) 와 B 의 `529c885`(cursor·clock·page·files store)·`a3b0f05`(crud page) 로, 6단계가 `6622d1e`(끝점·deps·계약 시험)·`b4500c3`(files 끝점)·`db44c63`(routers files 등록) 로 나뉘었다.

**worker-a**
1. `flush_or_conflict(session, message, *rows)` — 넣을 행을 인자로 받는다. SQLAlchemy 2.0.55 의 `begin_nested()` 가 SAVEPOINT 를 열기 전에 대기 변경을 flush 하므로(`_take_snapshot`), 행을 savepoint 안에서 add 해야 23505 뒤에도 바깥 요청 트랜잭션이 산다. 시험 `test_flush_or_conflict_keeps_outer_transaction` 추가. Design 5절 5 문구를 문서 커밋에서 맞췄다.
2. 계획에 없던 시험 `test_admin_login_missing_or_malformed_bearer_401` 추가.
3. `Settings`: 빈 문자열 `FILE_STORE_ROOT` 는 None(미구성)으로 본다(`Path("")` 가 현재 폴더가 되는 것을 막음). 수명·잠금 칸은 1 이상만.
4. 429 응답에 `Retry-After`(login_lock_minutes×60).
5. argon2 해시·대조는 `asyncio.to_thread` 로.
6. `sessions.create_session` 은 lifetime 을 인자로 받고 설정은 login 이 읽는다.
7. `crud/scope.py` 는 service 를 import 할 수 없어 `Subject` Protocol + `OwnerCheck=(session, subject, owner_id)→bool`.
8. `stored_file.owner_id` 는 BigInteger, key 는 crud 가 `token_urlsafe(16)` 로 만든다. `email_verification.code_hash` 는 NULL 허용(발급 전).
9. deps 에 `bearer_token` 을 공개해 logout 이 쓴다.
10. 잠금 판정은 (i) 그대로 창 안 실패 수만 센다 — 성공 로그인이 실패 수를 지우지 않는다(리뷰 확인 요청).

**worker-b**
1. `store.path_for(root, sha256)` — 계획의 `path_for(sha256)` 에 root 인자를 더했다(루트는 설정에서 온다).
2. `keyset_page(session, stmt, cursor, limit)` — crud 규칙(첫 인자 session)대로 session 을 더했고 반환은 `(items, next_cursor, has_more)` 튜플, 정렬은 (created_at, id) 내림차순 하나.
3. `store_bytes(root, data) -> sha256` 은 디스크만 다룬다. stored_file 행은 호출자가 `crud.insert_stored_file` 로 넣는다.
4. 관리 명령 `run` 은 async. create_admin 은 `ask=` 로 getpass 를 주입받고, file_gc 는 settings 를 셋째 인자로 받는다. 모르는 인자는 값을 찍지 않고 2(`--password <값>` 이 stderr 에 새지 않게). file_gc 는 지우기 직전 mtime 을 다시 본다.
5. `scripts/__init__.py` 를 만들지 않았다(이름 공간 패키지로 `python -m scripts.x` 와 pytest import 둘 다 된다).
6. 1부 파일 4개의 ruff format 정리를 `a3b0f05` 에 함께 넣었다(동작 변화 없음).
7. 문서: plan.md T1 착수 조건에 "= 이 가지의 approve 커밋(충족)" 을 T0b 전례대로 더했다. Design 5절 8 의 `service/auth.issue_email_code` 를 실제 경로 `service/auth/email_code.py` 로. 5절 9·10 은 서명을 적지 않아 그대로. spec 6행 강제 칸 "시험(예정)" → "시험(T1 일부, T2b 예정)". 리드가 A 의 실제 이름 목록을 늦게 넘겨 Design 반영이 두 커밋(`24e81c3` · `5688f82`)으로 나뉘었다: 1절 429 + `Retry-After` · 2절 argon2id · 4절 0002 code_hash NULL 허용 · 5절 8·13 `classfit.service.auth.email_code` · 5절 15 `app.dependency_overrides[classfit.app.deps.today]`. 서명·제약 이름 목록은 Design 본문에 넣지 않았다(코드가 정본).
8. `crud/page.py` 커서의 id 값이 INTEGER 로 캐스트되던 것을 BIGINT 칸 타입을 따르게 고쳤다(a3b0f05).

**대조 실험(worker-a, 임시 clone, 사본 삭제)**: ① `raise unauthorized()` 로 바꿈 → `test_auth_attempt_row_survives_401` 빨강 ② sqlstate 비교 제거 → `test_flush_or_conflict_check_is_500` 빨강 ③ 잠금 세기에서 client 조건 제거 → `test_auth_lockout_other_client_not_locked` 빨강 ④ 0002 의 learner_course CHECK 삭제 → `test_auth_session_*` 2건 빨강. 계약 ②(worker-b): service.auth → service.files import 를 넣으면 `2. service 구성요소는 서로 모른다 BROKEN`.

**리뷰 반영 커밋(계획 밖 변경)**
- `3047f7a`(A): login_id 제어 문자 422(`no_control_chars` AfterValidator) · 잠금 advisory lock — 지시는 login.py 의 SQL 한 문장이었으나 계층 규칙(raw SQL 은 crud)대로 `crud/auth.py::lock_attempt_key(session, *, kind, subject_hash, client)` 로 두고 `admin_login` 맨 앞에서 부름 · `make_engine` 에 `hide_parameters=True` 기본값. 시험 `test_admin_login_control_chars_in_login_id_422` 추가. 전체 73 passed.
- `584bd65`(B): files key 모양 밖은 같은 404 · `X-Content-Type-Options: nosniff` + `Content-Disposition: attachment; filename="<key>"` · 바이트 없는 행은 sha256 앞 12자만 로그 + problem 500 `/problems/internal` · `decode_cursor` 는 `type(i) is int and 0 < i < 2**63` 아니면 ValueError · outbox_preview 미리 보기 본문 `인증 코드: ******` · Design 5절 1 `DbSession`(app/deps.py) 줄 번호 제거. 시험 `test_files_malformed_key_404`·`test_files_missing_bytes_500`·`test_email_code_preview_masks_digits` + 커서 사례 2 추가. 대조 실험(고침 3곳 되돌림): 3 failed(DataError · 절대 경로 든 RuntimeError · 본문에 6자리).

**중간 커밋이 빨갛던 구간(reviewer Important 1)**: ⓐ `13b73ab`~`a3b0f05` 는 `test_db_email_code.py` 가 아직 없는 `scripts.outbox_preview` 를 import(워커 병렬 분할 때문) ⓑ `6622d1e`~`b4500c3` 는 `expected_paths.txt` 에 `/v1/files/{key}` 가 있는데 ROUTERS 에 files 가 없음. 이력은 다시 쓰지 않았다. 다음 태스크부터는 다른 워커 산출물에 기대는 시험·기대 파일은 그 산출물 커밋 뒤에 커밋한다.

**check_task_order 예상과 실제**: 계획은 T0b 병합 전 FAIL 을 예상했으나 승인 전에 T0b 가 이미 master 에 있어 approve 시점부터 OK 였다(plan 커밋 직후에만 FAIL 9건).




---

# Resources

- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §1 · §3 D2 · §5.2 T1 행 · §6 · 부록 B T1(엔드포인트·시험 세부) · C · D · F · I-10·I-12 · J(T1 · R5) · 변경 기록 N4·N5·N6·N10·N12·N13. 저장소 루트 기준 경로이고 `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 저장소 문서: [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) · [`docs/process/plan.md`](../process/plan.md) · [`docs/process/spec.md`](../process/spec.md) · [`docs/process/adr/ADR-002-learner-session.md`](../process/adr/ADR-002-learner-session.md) · [`docs/process/adr/ADR-003-external-ports.md`](../process/adr/ADR-003-external-ports.md) · [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) · [`docs/plans/T0a-sdlc-bootstrap.md`](T0a-sdlc-bootstrap.md) · [`docs/plans/T0b-sdlc-okf.md`](T0b-sdlc-okf.md)(형식 본보기).
- 백엔드 안내서 `2026-10-21-backend-framework-porting-guide.md` §2 · §3.1 · §3.2 · §3.4 · §3.5 · §7(저장소 루트).
- 뼈대 코드(가지 T0b-sdlc-okf, 2026-10-22): `src/classfit/{core/config.py, core/errors.py, database/session.py, models/base.py, models/audit.py, crud/audit.py, app/deps.py, app/errors.py, app/routers.py, app/endpoints/health.py, main.py}` · `alembic/versions/0001_audit_log.py` · `alembic/env.py` · `tests/conftest.py` · `tests/contracts/conftest.py` · `tests/contracts/test_tx_boundary.py` · `tests/fixtures/probe_routes.py` · `tests/stale_patch_guard.py` · `pyproject.toml` · `Makefile` · `scripts/check_task_order.sh` · `.claude/hooks/deny-deps.sh`.
