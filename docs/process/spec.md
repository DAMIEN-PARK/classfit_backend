---
type: Spec
title: "Spec: ClassFit 스펙 색인"
description: ClassFit 의 정본 문서 색인(저장소·외부, 외부는 sha256), 원칙별 정책이 코드 어디에 있는지 대조표, 우려 처리 기록, 스펙 변경 규칙
date: 2026-10-21
tags: [spec, classfit, index, policy, sdlc]
Archives: false
URL: ""
---

# ClassFit 스펙 색인

요구사항과 설계는 아래 정본 문서에 있다. 여기에 옮겨 적지 않는다. 어떤 문서가 무엇의 정본인지 모호하면 이 표가 답이다(SDLC §6.4).

- 정본 순서(r3 §0 · §3 원칙 ②): 제품은 기획안 v3, 규칙·표·결정은 Design 문서, 엔드포인트는 `/v1/openapi.json`(코드에서 생성, src/classfit/main.py:54), 문항·산식·상태 규칙은 코드 한 곳이다. 시안은 화면 참고이고, 기획안과 어긋나면 기획안이 기준이다(r3 §2 가정 1).
- `scripts/check_docs.sh` 가 1절과 2절 표를 읽는다. 읽는 모양은 4절 6번에 있다.

## 1. 정본 색인

외부 행은 저장소에 커밋하지 않은 파일이다. 경로는 저장소 루트 기준이고, 검토한 판을 sha256 으로 고정한다(2026-10-22 에 `shasum -a 256` 으로 다시 재서 T0b 계획의 확인값과 같음을 봤다).

| 영역 | 파일 | 위치 | sha256 | 버전·상태 | 승인·근거 | 함께 바뀌어야 하는 문서 |
|---|---|---|---|---|---|---|
| 제품 정본 | `기획/BCTONE_기획안_v3.html` | 외부 | `54b8c90730d06641d2add5beaa419bad450c9549db6723bde7d06050ea54e9d1` | v3(2026-10-21) · 정본 · 미추적 | r3 §2 가정 1 | [intent.md](intent.md) · 이 색인 |
| 파이프라인 | `기획/BCTONE_파이프라인_v3.html` | 외부 | `4519cb4b371a5fa028e85e98261a51c0e1992f588bfaf4028c65bf70eafe729b` | v3 · 기획안과 어긋나면 기획안이 기준 · 미추적 | r3 §2 가정 1 | [Design](2026-10-21-phase1-backend-design.md) |
| 시안 관리자 | `시안/관리자.html` | 외부 | `c14d5e9631fe0c411c2af5ff254195d87dfef7c7412bf4a137c17aaa9f781be2` | 참고 · 정본 아님 · 미추적 | [ADR-001](adr/ADR-001-mockups.md) | [시안 검토](research/2026-10-21-mockup-review.md) |
| 시안 강사 | `시안/강사.html` | 외부 | `041260b79b1dfcac6001f38f0e76ab2e7b21849fa065aa2454ac4cc0b0187e29` | 참고 · 정본 아님 · 미추적 | [ADR-001](adr/ADR-001-mockups.md) | [시안 검토](research/2026-10-21-mockup-review.md) |
| 시안 학습자 | `시안/학습자.html` | 외부 | `ea33694171a9823cfd6dbd65cb0ac89c1939ecf61e62d20c5634a0351a037551` | 참고 · 정본 아님 · 미추적 | [ADR-001](adr/ADR-001-mockups.md) | [시안 검토](research/2026-10-21-mockup-review.md) |
| 제품 의도 | [`docs/process/intent.md`](intent.md) | 저장소 | git 추적 | approved | DAMIEN-PARK, 승인 빈 커밋 `approve: T0b` | 이 색인 · [plan.md](plan.md) |
| 1차 백엔드 의도 | [`docs/process/intents/2026-10-21-phase1-backend.md`](intents/2026-10-21-phase1-backend.md) | 저장소 | git 추적 | approved | DAMIEN-PARK, 승인 빈 커밋 `approve: T0b` | [Design](2026-10-21-phase1-backend-design.md) · [plan.md](plan.md) |
| 시안 검토 | [`docs/process/research/2026-10-21-mockup-review.md`](research/2026-10-21-mockup-review.md) | 저장소 | git 추적 | 기록 · 결정 아님 | r3 부록 A1~A5 | [ADR-001](adr/ADR-001-mockups.md) · [Design](2026-10-21-phase1-backend-design.md) |
| 요구 목록 | [`docs/requirements/2026-10-21-요구정의서.md`](../requirements/2026-10-21-요구정의서.md) | 저장소 | git 추적 | v1.0 검토용 · 정본 아님 | T0a 계획 "계획과 다르게 한 것" 12번(사용자 지시) | 이 문서 3절 |
| 설계 | [`docs/process/2026-10-21-phase1-backend-design.md`](2026-10-21-phase1-backend-design.md) | 저장소 | git 추적 | 승인 · 1차 규칙·표·결정의 정본 | r3 플랜 승인(2026-10-21) | [plan.md](plan.md) · 태스크 계획 · 이 문서 2절 |
| ADR-001 시안 | [`docs/process/adr/ADR-001-mockups.md`](adr/ADR-001-mockups.md) | 저장소 | git 추적 | 승인 | r3 §4 · 부록 A6 | [Design](2026-10-21-phase1-backend-design.md) 1절 |
| ADR-002 학습자 세션 | [`docs/process/adr/ADR-002-learner-session.md`](adr/ADR-002-learner-session.md) | 저장소 | git 추적 | 승인 | r3 §4 · §1.1 ④ | [Design](2026-10-21-phase1-backend-design.md) 1·2절 |
| ADR-003 외부 포트 | [`docs/process/adr/ADR-003-external-ports.md`](adr/ADR-003-external-ports.md) | 저장소 | git 추적 | 승인 | r3 §4 | [Design](2026-10-21-phase1-backend-design.md) 1·3절 |
| ADR-004 공개홈 | [`docs/process/adr/ADR-004-public-home.md`](adr/ADR-004-public-home.md) | 저장소 | git 추적 | 승인 · r3 §7-1 답에 따라 다시 봄 | r3 §4 · 부록 A5 | [feature intent](intents/2026-10-21-phase1-backend.md) |
| 태스크 순서 | [`docs/process/plan.md`](plan.md) | 저장소 | git 추적 | T0a·T0b·T1·T2a·T2b·T3·T4·T5·T6·T7·T8 병합 · T9a 진행 중 | r3 §5.2 | 태스크 계획 · [agent.md](agent.md) |
| 에이전트 편성 | [`docs/process/agent.md`](agent.md) | 저장소 | git 추적 | 승인자 DAMIEN-PARK | r3 §5.1 · 부록 E11 | CLAUDE.md · `.claude/settings.json` |

## 2. 정책 대조표

r3 §3 원칙 ①~⑤ 와 기획안 03 운영 원칙 중 서버가 지킬 것(2·5·10·12·13)이다. "어디에 코드로 있는가" 칸은 지금 있는 장치를 실제 경로로 적는다. 코드가 아직 없으면 `예정: T<n> + 시험 이름` 으로 적고, 이름은 [Design 부록 A](2026-10-21-phase1-backend-design.md) 대응표의 것을 쓴다.

| # | 정책 | 어디에 코드로 있는가 | 강제·권고 | 소유자 |
|---|---|---|---|---|
| 1 | r3 원칙 ① 계획 먼저, 승인은 사람만 | `.claude/hooks/deny-approval.sh`(에이전트 커밋의 승인 표시 차단) · `scripts/check_task_order.sh`(가지는 plan → approve → T 커밋 순서, master 는 병합 커밋만. pre-push·CI) · `.githooks/pre-commit`(master 직접 커밋 차단) · `.githooks/pre-merge-commit`(스크립트 밖 master 병합 차단) · `.claude/settings.json` deny(병합·push·reset·훅 우회) · `scripts/merge_task.sh`(승인자 전용) · [agent.md](agent.md) 4절 | 강제(훅·CI). 같은 계정의 위조는 기계로 다 막지 못한다 | DAMIEN-PARK |
| 2 | r3 원칙 ② 원본은 한 곳 | 이 문서 1절 + `scripts/check_docs.sh` ①②(색인 경로 실재 · 외부 정본 sha256, pre-push 는 `CLASSFIT_REQUIRE_EXTERNAL=1`) · `src/classfit/main.py`(`/v1/openapi.json`) · `tests/contracts/test_api_openapi.py`(E-13, OpenAPI 경로 집합 = `tests/contracts/expected_paths.txt`, `/v1/_probe` 없음) · `tests/unit/test_schedule_rules.py`(`test_golden_schedule_`, 일정 규칙 `src/classfit/service/rules/schedule.py` 가 시안 일정 함수와 같은 값) · `tests/unit/test_diagnosis_rules.py`(`test_golden_score_` 3, T9a — 산식 `src/classfit/service/rules/diagnosis.py` · 문항 `diagnosis_items.py`·`diagnosis_items_34.py` 가 시안 `calc`·`AREAS` 와 같은 값, `scripts/golden/extract.mjs` 가 `AREAS` 블록·`calc` 를 돌린다) | 강제(pre-push·CI) | DAMIEN-PARK |
| 3 | r3 원칙 ③ 판정은 서버가, 규칙마다 시험 1개 이상 | [Design 부록 A](2026-10-21-phase1-backend-design.md) 대응표 + `scripts/check_docs.sh` ④(병합된 T 의 행마다 `tests/` 에 def) · `tests/conftest.py`(시험 DB 가 없으면 pytest.fail, skip 금지) · `.claude/hooks/protect-tests.sh`(버그 픽스 모드에서 tests 편집 차단) | 강제(check_docs·CI test) | DAMIEN-PARK |
| 4 | r3 원칙 ④ 지금 대표 데이터로 검증 | `tests/conftest.py`(라이브 Postgres, 세션마다 downgrade base → upgrade head) · `.github/workflows/ci.yml` test 잡(postgres:17) · `scripts/golden/extract.mjs`(합성 사례로 시안 일정 함수를 돌린다, TZ Asia/Seoul 고정) · `scripts/golden/check.sh`(재추출 대조, pre-push) · `tests/unit/test_schedule_rules.py`(`test_golden_schedule_`, CI 는 커밋된 `tests/fixtures/golden.json`) · `tests/unit/test_diagnosis_rules.py`(`test_golden_score_` 3 — 진단 산식 합성 사례 일곱 `score`, E-12, T9a) | 강제(CI test) | DAMIEN-PARK |
| 5 | r3 원칙 ⑤ 강제는 기계로 | `Makefile` verify(editable-check → gate → lint → lint-imports → test, T0b 에서 끝에 okf) · `.githooks/pre-push` · `.github/workflows/ci.yml` gates·test · 금지 의존성 `pyproject.toml` banned-api(ruff TID251) · `.claude/hooks/deny-deps.sh` · `scripts/gate.sh` · 차단기 회귀 `scripts/test_gate.sh` · `.claude/hooks/test_hooks.sh` · 문서 `scripts/okf/guard.sh`(T0b) · `scripts/check_docs.sh` | 강제(훅·CI) | DAMIEN-PARK |
| 6 | 기획안 원칙 2 수강생의 문은 초대코드 하나(가입·비밀번호 없음) | [ADR-002](adr/ADR-002-learner-session.md) · `tests/integration/test_db_auth_session.py`(수강생 세션은 course_id 필수, auth_session CHECK) · `tests/contracts/test_api_enter.py`(`test_p3_*` 9건 · `test_reissue_*` 2건 · `test_cross_course_portal_403` · `test_enrollment_name_isolated`, E-10 13건. 입장 판정 `src/classfit/service/enroll/enter.py`) · `tests/integration/test_db_enroll.py`(learner 이메일 lower 유일 · 등록은 `enter_course` 한 곳) | 시험(T1·T2b) + ADR | DAMIEN-PARK |
| 7 | 기획안 원칙 5 첨부가 없거나 공개가 꺼진 세션은 "준비 중" | `tests/contracts/test_api_portal.py`(`test_portal_locked_` 3건: 카드 잠김 · 잠긴 세션의 첨부 목록·`href` 403) · 카드 판정 `src/classfit/service/rules/portal.py` 의 `card_state` · 파일 판정 `src/classfit/crud/scope.py`(`session_attachment` 는 수강생에게 세션 `is_open` 일 때만 · 강사 파일 열람은 범위 강의의 내 세션 ∨ 열린 세션, T6 — `tests/contracts/test_api_my_attachments.py` 의 `test_attachment_owner_kind_instructor_files`) · `tests/unit/test_enter_rules.py`(`test_enter_card_state_needs_open_and_attachment`) | 시험 | DAMIEN-PARK |
| 8 | 기획안 원칙 10 응답은 개인과 연결해 보여 주지 않는다 | REVIEW.md 보안 패스(원칙 10 항목) · [Design](2026-10-21-phase1-backend-design.md) 1절 만족도 공개 범위 · `tests/contracts/test_api_portal.py`(`test_no_personal_keys_portal`, 수강생·관리자 포털과 첨부 목록에 `email`·`name`·`dept`·`learner_id`·`enrollment_id` 키 0) · `tests/integration/test_db_pool.py`(`test_no_personal_keys_catalog`, 공개 카탈로그 질의 `src/classfit/crud/catalog.py` 의 `published_catalog()` 출력 키 집합에 강사 id·이름·이메일 없음) · `tests/contracts/test_api_pool.py`(`test_pool_list_other_own_course_has_no_author_keys`, 강사용 풀 응답에 작성자 키 없음) · 포털 강사 칸은 `instructor_name` 하나(T5, `tests/contracts/test_api_assign.py` 의 `test_assign_portal_instructor_name` 이 카드·첨부·섹션·강의 키 집합을 정확히 잰다) · 강사 명단에 이메일 없음(T6, `tests/contracts/test_api_my_course_views.py` 의 `test_instructor_view_roster_minimal` 이 항목 키 집합을 정확히 잰다 — T8 뒤 명단은 이름·부서·등록일 + 설문 응답 여부(bool \| null)이고 답과 잇는 칸은 없다) · 교육 기록·사진은 포털·수강생 경로에 없다(T7, `tests/contracts/test_api_records.py` 의 `test_record_portal_has_no_record_keys` 가 수강생·관리자 포털과 강사 포털 미리 보기의 재귀 키에 기록·사진 칸이 없고 키 집합이 T5 허용 집합과 같음을 잰다, NFR-002) · 설문 결과(I7·A5)·포털 배너·명단 응답 여부 칸에 개인 키·제출 시각이 없다(T8, `tests/contracts/test_api_survey_learner.py` 의 `test_no_personal_keys_i7`·`test_survey_portal_banner`·`test_survey_roster_responded` 와 `tests/contracts/test_api_surveys.py` 의 `test_no_personal_keys_a5` — 결과는 재귀 키 집합 == 허용 집합 ∧ 금지 집합 ∩ ∅, E-14. 집계는 `src/classfit/service/rules/survey_stats.py`, 결과 읽기는 `src/classfit/crud/survey_response.py` 가 답 배열만 고른다) · 공개 진단 링크 응답(`/v1/ax/{token}` — 문항·410·404·422)에 담당자·연락처·받는 분·응답자 이메일·점수·회차 번호가 없고 제출 응답은 `{phase, submitted_at}` 뿐이며, 토큰은 로그·`instance` 에 `{token}` 으로만 남고 access log 는 `make run`(`--no-access-log`) 기준으로 남지 않는다(T9a, `tests/contracts/test_api_ax.py` 의 `test_diag_link_public_get_states`·`test_diag_link_submit_creates_review_round`·`test_diag_link_public_token_not_logged`·`test_diag_link_public_500_redacted`. 가리기는 `src/classfit/app/errors.py` 의 `request_path`·`TokenRedactFilter`) | 리뷰 + 시험(T2b·T4·T5·T6·T7·T8·T9a) | DAMIEN-PARK |
| 9 | 기획안 원칙 12 실제 고객사명은 시안·데모 데이터에 쓰지 않는다 | `scripts/gate.sh` 4번(금지 용어 `scripts/forbidden_terms.txt`, 범위 src·tests·alembic·scripts·docs·루트 md, 출력은 file:line 만) · pre-push·CI 의 `CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1` · `scripts/check_secrets.sh` · CLAUDE.md Rules · `scripts/golden/extract.mjs`(합성 사례만 돌려 회사명·인명이 처음부터 없다. `tests/fixtures/golden.json` 은 사례 id·숫자·날짜·시각뿐) | 강제(CI) | DAMIEN-PARK |
| 10 | 기획안 원칙 13 강의는 관리자가 개설하고 강사를 배정한다. 강사는 구조를 만지지 않는다 | CLAUDE.md Rules 단일 진입점 `open_course()`(`src/classfit/service/courses/open.py`) · `tests/integration/test_db_open_course.py`(`test_courses_open_single_entry`) · `tests/contracts/test_api_assign.py`(`test_assign_`: 미승인 배정 409 등, 판정 `src/classfit/service/courses/assign.py`) · `tests/contracts/test_api_my_courses.py`(`test_instructor_session_`: 제목 PATCH 422 · 남의 세션 403, 판정 `src/classfit/service/courses/mine.py`) · 강사 첨부 쓰기는 배정 세션만(`tests/contracts/test_api_my_attachments.py` 의 `test_attachment_`, 판정 `src/classfit/service/files/my_attachments.py`) | 시험(T2a·T5·T6) | DAMIEN-PARK |

정책이 바뀌면 소유자가 정하고, 같은 커밋에서 훅·스크립트·문서를 고치고, 이 표의 행을 갱신한다.

## 3. 우려 사항 처리 기록

r3 부록 A2 데이터 계약 차이 11건, A3 시안 전용 기능 5종, §2 가정 7(기획안 내부 모순), 요구정의서 §10 DEC-001~016 이다. 정책 # 는 2절의 번호다. DEC 행의 원문과 영향은 [요구정의서](../requirements/2026-10-21-요구정의서.md) §10 에 있다.

| 일자 | 우려 | 정책 # | 처리 | 상태 |
|---|---|---|---|---|
| 2026-10-21 | A2-1 Course 칸 이름·값 표기가 시안끼리, 시안과 기획안이 다르다(title·name, client·company, method·mode, 시수, 상태, 날짜 구분자) | 2 | title·client_name·method·hours_per_person(int)·status prep·running·ended, ISO 8601 | 결정(r3) · T2a 반영(0003 `course`) |
| 2026-10-21 | A2-2 InviteCode 가 기획안은 별도 개체, 관리자 시안은 Course 에 납작, 강사 시안은 객체 | 2 | 별도 표, 재발급 이력은 replaced 행 | 결정(r3) · T2a 반영(0003 `invite_code`) |
| 2026-10-21 | A2-3 Enrollment 를 관리자는 수만, 강사는 목록으로, 기획안은 이메일로 사람을 묶는다 | 2 | learner(이메일만) + enrollment(이름·부서), 응답 여부는 계산 | 결정(r3, ADR-002) · T2b 반영(0004 `learner`·`enrollment`) |
| 2026-10-21 | A2-4 Session·Attachment 칸 이름이 넷(att·files·attachments·keys), 종류 img·image | 2 | keywords[], kind=image, href | 결정(r3) · T2b 반영(0004 `session_attachment`, kind 5종 pdf·office·html·link·image · 응답 `href`) |
| 2026-10-21 | A2-5 Diagnosis·DiagLink 상태 값이 다르다 | 2 | draft·review·final / open·submitted·revoked, 만료는 계산 | 결정(r3) · T9a 반영(0010 CHECK `diagnosis.status`·`diag_link.status` · 만료는 open ∧ `expires_on` < 오늘로 계산, `service/rules/diagnosis.py` 의 `link_state`) |
| 2026-10-21 | A2-6 Company 규모가 시안 5구간, 문의 4구간 | 2 | 회사 5구간, 문의 4구간 그대로 | 결정(r3) · T9a 반영(0010 `company.size` CHECK 코드 5 `lt10`·`s10_49`·`s50_99`·`s100_299`·`ge300` — `COMPANY_SIZES`) · 문의는 T9b |
| 2026-10-21 | A2-7 강사 서류가 기획안 3종, 시안 4종 + 계약서 + 기타 | 2 | document_type 표, 시드 3종. 최종 항목은 DEC-006 | 1차 결정(r3) · T3 반영(0005 `document_type` 시드 3종 resume·cert·pledge) · DEC-006 열림 |
| 2026-10-21 | A2-8 Capability 의 시안 confirmed·fix | 2 | 1차는 기획안대로 | 결정(r3) · T4 반영(결정 x: `capability` 는 강사 × 과정 한 행 + 메모·파일, confirmed·fix 없음) |
| 2026-10-21 | A2-9 Pool 직무군이 문자열과 배열로 다르다 | 2 | job_groups[] | 결정(r3) · T4 반영(결정 xiv: 0006 `pool_course`·`curriculum` 의 `job_groups` text[] ≥ 1, 값 집합 13) |
| 2026-10-21 | A2-10 심화 과정 시드에 id·pub·active 가 없다 | 2 | 표에 둔다 | 결정(r3) · T4 반영(결정 xvii: 0006 `advanced_course`(id·pub·active), 시드 없음 — 현행 카드는 `import_ax_catalog` 의 advanced 구간으로 이관) |
| 2026-10-21 | A2-11 입장 부서가 강의 섹션과 공통 16 + 직접 입력으로 다르다 | 2 | 기획안대로. 선택지 확정은 DEC-016 | 1차 결정(r3) · DEC-016 열림 |
| 2026-10-21 | A3-1 강사 일정·배정 겹침 알림이 시안에만 있다 | 해당 없음 | 1차 제외, intent 후보로 기록 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-2 시수·월별 정산 확정이 시안에만 있다 | 해당 없음 | 1차 제외. 시수는 교육 기록의 실시 시각으로 나중에 계산 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-3 서류 종류 설정이 시안에만 있다 | 해당 없음 | 종류 표만, 편집 API 는 2차 | 1차 일부 · DEC-015 |
| 2026-10-21 | A3-4 강사위촉계약서가 시안에만 있다 | 해당 없음 | 1차 제외 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-5 가능 과정 확인·보완 요청이 시안에만 있다 | 해당 없음 | 1차 제외, reviewed 토글만 | 1차 제외 · DEC-015 · T4 반영(결정 v·x: 관리자 PATCH 의 `reviewed` 토글만, 확인·보완 요청 없음) |
| 2026-10-21 | 가정 7 기획안 내부 모순: 과정 풀 절 "DB에는 고유 과정과 가능 표시만" ↔ 원칙 6, 고유 과정 "삭제" ↔ 파이프라인 9 "삭제 없음" | 2 | AX 과정도 DB 원본, 고유 과정 삭제는 사용 중지, 패키지명 classfit 유지 | 결정(r3 §2 가정 7) · T4 반영(결정 ii·xi: AX 과정은 `import_ax_catalog` 로 DB 에 넣고 고유 과정·커리큘럼 DELETE 는 active=false) |
| 2026-10-21 | DEC-001 만족도 100점 환산식이 관리자·강사 시안에서 다르다 | 2 | 단일 환산식 선택 권고, 긍정률은 실제 4·5점 비율. T8 기본: 100점 = 평균 × 20 · 긍정률 = 실제 4·5점 비율(결정 x) · 대안 (평균 − 1) / 4 × 100 열림 · 기획안 I7 :660-665 도 산식 없이 "현행 `survey_stats.py` 출력 형식"(저장소 밖 현행 스크립트)을 가리킨다 — 그 식이 오면 그것으로 | 결정 필요 |
| 2026-10-21 | DEC-002 관리자 일정과 강사·학습자 시간 함수의 점심·요일 처리가 다르다 | 2 | 관리자 일정 정의로 통합 권고, 시수 기준 확정 | 결정 필요 |
| 2026-10-21 | DEC-003 진단 17지표 최저 응답 총점 160 이라 L1 이 불가능하다 | 2 | 단계 점수 체계·레벨 경계를 기획자가 확정, 임의 변경 금지. T9a: 산식 그대로 — golden `dg-all-1` 이 160 → L2 를 고정(`test_golden_score_levels`) · 17지표를 다 답하기 전이면 응답 `level` null | 결정 필요 |
| 2026-10-21 | DEC-004 학습자 시안은 강의를 즉시 전환하고 전역 이름을 쓴다 | 6 | ADR-002 로 결정됨. 시안 UI 수정 대상 | 결정(ADR-002) |
| 2026-10-21 | DEC-005 강사 반려·정지 제한, 재신청, 관리자 초기 비밀번호가 시안에서 미완성 | 해당 없음 | 공개홈·기존 설계와 대조해 인증·복구·정지 범위 확정. T3 기본값(계획 결정 vi·vii·viii·xii): 반려는 사유 1~500자 필수 · 반려 강사는 로그인해 사유를 보고 `:reapply` 로 대기에 돌아간다 · 정지는 산 세션 폐기 + 로그인 403 · 해제는 승인으로. 관리자 초기 비밀번호는 T1 `create_admin` 그대로. T5 기본: 정지 강사의 기존 배정 유지, 새 배정은 승인만(결정 viii·ix) | 결정 필요 |
| 2026-10-21 | DEC-006 필수 서류가 시안 4종 + 계약서, r3 는 기획안 3종 시드 | 해당 없음 | 초기 제출 항목·예외·필수 정책 확정. 1차 시드는 3종(r3 §7-2). T3 기본값(계획 결정 xiv·xviii): 0005 시드 이력서·자격증/경력증명·강사 서약서, 셋 다 필수 · PDF 만 · 서류는 승인 조건이 아니다 | 결정 필요 |
| 2026-10-21 | DEC-007 실제 시각 공란이면 계획 시간으로 집계, 확정 후 수정 흐름이 불분명 | 해당 없음 | 실제 시간 필수 여부·수정 이력 확정. 정산은 1차 제외 | 결정 필요 |
| 2026-10-21 | DEC-008 보관 강의를 관리자 시수 집계에서 뺀다 | 해당 없음 | 역사적 집계 유지 권고, 보관 후 규칙 확정 | 결정 필요 |
| 2026-10-21 | DEC-009 비공개 차시 숨김 안내와 학습자 렌더러 판정이 다르다 | 7 | 비공개 카드 숨김·노출 범위 확정. 자료 접근 차단은 공통 | 결정 필요 |
| 2026-10-21 | DEC-010 강의안·서류 크기 검증과 교체 UI·HTML 구성이 미정 | 해당 없음 | 확장자·MIME·크기·교체 방식 확정. 1차 상한은 기획안 I4. T6 기본: 기획안 확장자 표 · 첫 바이트 · 종류별 상한 설정 칸 · 교체는 같은 행 file_id 바꿈(결정 iii·iv·vii) · T7: 사진은 T6 이미지 판정·`ATTACHMENT_IMAGE_MAX_MB`, 15장·1024px 변환 없음 | 결정 필요 |
| 2026-10-21 | DEC-011 1차는 outbox·501, 시안은 발송·열기·PDF 를 표현 | 해당 없음 | ADR-003 의 1차 제한은 결정됨. 업체·재시도·뷰어·출처는 후속. T6: HTML 패키지 열기 501 `/problems/not-implemented` | 1차 결정(ADR-003) · 후속 열림 |
| 2026-10-21 | DEC-012 양식 자유 편집과 학습자·결과 렌더러의 고정 문항이 다르다 | 해당 없음 | 배포 복제본 기준 동적 입력·집계 권고, 수정 범위 확정. T8: 배포 복제본 기준 동적 입력·집계 · 응답 1건 뒤 문항 잠금 · 비교표는 1차 밖(결정 v·vii·x) | 결정 필요 |
| 2026-10-21 | DEC-013 설문 분모·결측·강사 결과 공개 시점·최소 응답 수가 불충분 | 8 | I7 최소 5건은 제안값(Design 1절). 공개·소수 응답 정책 확정. T8 기본: 분모 = 조회 시점 등록 수 · 강사는 마감 뒤 + `survey_min_responses`(5) 이상 · 관리자 임계 없음(결정 xii·xiii) | 결정 필요 |
| 2026-10-21 | DEC-014 성능·보존 기간·브라우저·백업 기준이 없다 | 해당 없음 | 운영 규모·보존·파기 정책 확정. 사진 동의는 별도(r3 §7-6·7) · T7: 공개 표시 없음 · 관리자 ∨ 그 세션 담당 강사만 연다 | 결정 필요 |
| 2026-10-21 | DEC-015 시안 전용 5종이 시안에는 있고 r3 1차에서 빠졌다 | 해당 없음 | 시안 전체 요구로 유지. 착수 때 범위 변경 또는 후속 배치 결정 | 결정 필요 |
| 2026-10-21 | DEC-016 과정 시안 데이터가 144개 중 42개 예시, 부서 선택지 코드가 다르다 | 2 | 이관 원본·개수·ID 와 입장 부서 선택지 확정. T4: 원본은 외부 JSON 경로 인자, 저장소는 합성 표본만(결정 ii) | 결정 필요 |
| 2026-10-22 | 요구정의서 CAT-006(:172)·CAT-009(:175)·UAT-002(:420)·전이표(:292) 는 강사가 검토 뒤 고치면 비공개로, 미검토는 카탈로그 제외라 하고, Design 부록 A T4 3행·r3 317·기획안 :567 은 pub·active 유지라 한다 | 2 | 정본(Design·기획안) 대로 pub 유지. 요구정의서는 정본 아님(1절) | T4 결정 vi·vii 기본 · 대안 ③ 열림 |
| 2026-10-22 | 시안 강사.html:1090·요구정의서 CRS-007(:187)·:98 은 강사가 세션 제목(주제)을 고치게 하고, 기획안 :205·Design 부록 A T5 는 설명·키워드·공개·첨부만이라 한다 | 10 | 정본(기획안·Design) 대로 제목 PATCH 422 | T5 결정 xiii |
| 2026-10-22 | 배정 알림의 트리거: 요구정의서 NTF-001(:280)·기획안 :775·:320·시안 관리자.html:1787 은 관리자가 누르는 「배정 알림 보내기」, r3 318·기획안 8-5 :968 은 배정 이벤트 | 해당 없음 | 배정 이벤트마다 새 강사에게 outbox 1행(r3 318) | T5 결정 xv 기본 · 대안 ②(`:notify`) 열림 |
| 2026-10-22 | 기획안 :774 는 풀에서 고를 때 기본 강의안이 따라온다고 하고 :564·:573 은 배정될 때 붙는다고 한다(고르는 시점엔 강사가 없어 원본을 못 정한다) | 해당 없음 | 배정 때 자동 첨부 | T5 결정 vi·x 기본 · 고르며 배정하는 대안 ②·③ 이면 고를 때도 붙음 |
| 2026-10-22 | 기획안 :909 는 세션 자료에 「원본 기본강의안 여부」 를 두고, Design 4절 0007 행(:88)은 `session_attachment` 를 바꾸지 않았다. 사본이 보통 첨부와 섞이면 T6 가 출처를 되살릴 수 없다(codex 1차 #6) | 2 | 0007 이 `session_attachment.origin`(NULL · CHECK 원본 owner_kind 셋)을 더해 사본마다 저장, 응답 노출은 T6 | T5 결정 xi 기본 · 대안 ①(bool)·②(칸 없음) 열림 |
| 2026-10-22 | r3 §3 A2·Critic r2 (c)2 는 관리자 첨부 업로드를 T6 이후 남길지 T6 계획에서 정한다고 했다 | 해당 없음 | 남긴다(pdf·link, 담당 강사가 없는 세션의 예외 문). 강사와 같은 표·판정·잠금 | T6 결정 x 기본 |
| 2026-10-22 | 시안 kindOf(강사.html:1132)는 .ppt .doc .xls .hwp .hwpx .gif .svg 도 받고 기획안 :609-612 는 .pptx .docx .xlsx .csv · .png .jpg .webp 만 적는다 | 2 | 정본(기획안) 표 + 같은 JPEG 인 .jpeg | T6 결정 iii 기본 · 대안 ① 열림 |
| 2026-10-22 | 시안 useDefault(강사.html:1136)·MAT-001 은 강사가 「기본 강의안 붙이기」 로 과정 기본 자료를 가져오게 하고, r3 306 에는 그 끝점이 없다 | 해당 없음 | 1차는 T5 배정 때 자동 첨부만 | T6 범위 밖 |
| 2026-10-22 | 기획안 I6 :645·:648 · 요구정의서 ENT-008(:204) · 시안 강사.html:1168·:883 은 강사 명단에 수강생 이메일을 둔다 | 8 | 1차 강사 명단은 이름·부서·등록일만(메일 발송·xlsx 가 1차에 없어 쓸 곳이 없고, 연락처는 최소 노출) | T6 결정 xxi 기본 · 대안 ①(정본 그대로)·②(가린 이메일) 열림 |
| 2026-10-23 | r3 307 은 강사 사진 PATCH·DELETE 를 `/v1/me/sessions/{id}/photos` 에 둔다 | 해당 없음 | `/v1/me/photos/{photo_id}`(사진 하나를 가리킨다, T6 첨부 경로 꼴) | T7 결정 ii 기본 |
| 2026-10-23 | 요구정의서 PHO-001(:226)·권한 매트릭스(:103)·시안 관리자.html:769 는 관리자도 사진을 올리고 설명을 고친다, r3 307 에는 그 끝점이 없다 | 해당 없음 | 1차는 관리자 지우기·모아보기·내려받기 목록·확인 표시만 | T7 결정 viii 기본 · 대안 ① 열림 |
| 2026-10-23 | 시안 강사.html:1070 은 같은 강의 남의 차시 기록 내용·사진을 강사에게 흐리게 보인다, 권한 매트릭스(:102-103)는 본인 차시만 적는다 | 해당 없음 | 강사 기록 화면은 내 세션만(사진 초상권 미정 r3 §7-7) | T7 결정 x 기본 · 대안 ①② 열림 |
| 2026-10-23 | r3 307 의 사진 모아보기 `sort=`(시안 recent·date·name 관리자.html:2192)는 키셋 커서((created_at, id), `src/classfit/core/cursor.py`)와 함께 줄 수 없다 | 해당 없음 | 1차는 최근 올린 순 한 가지 + 화면이 쪽 안에서 묶는다 | T7 결정 xi 기본 · 대안 ① 열림 |
| 2026-10-23 | r3 308 은 배포를 `{course_ids, template_id, open_at?, close_at?}` 한 쌍과 PATCH 하나로 마감·다시 열기를 적고, 기획안 7절 :911·A5 :874 는 열림·닫힘을 일시와 상태 칸으로 둔다 | 해당 없음 | 열기·닫기 모드(`open {mode, date?}` · `close {mode, date?}`)를 잠근 강의마다 날짜 `open_on`·`close_on` 으로 풀고 상태는 `Today` 로 계산 + `:close`·`:reopen`(동작 접미사 규칙). 날짜로 닫힌 설문은 알림이 없다(워커 없음) | T8 결정 ii·iii·vi 기본 · 대안(시각 단위 · 날짜 한 쌍) 열림 |
| 2026-10-23 | SVY-009(:270) "마감 후 결과" 와 DEC-013 "마감/재개방 중 공개" 가 열려 있다 | 8 | 강사는 마감 뒤 + 최소 응답 수 이상일 때만, 관리자는 늘 | T8 결정 xii 기본 · 대안 ① 열림 |
| 2026-10-23 | NTF-002(:281)·기획안 알림 표 :970-971 은 예약 개방·닫힘 시점에 알림을, 닫힘은 강사·관리자에게 요구하고 1차에는 워커도 관리자 이메일 칸도 없다(ADR-003 · `src/classfit/models/admin.py`) | 해당 없음 | 배포 때 `survey_opened` 를 쌓고(예약도) 관리자가 닫을 때만 강사에게 `survey_closed` · 날짜 마감 알림과 관리자 수신은 2차 워커·관리자 이메일 칸 | T8 결정 xvii 기본 · 대안 ①·③ 열림 |
| 2026-10-23 | ENT-008(:204)·시안 강사.html:1168·기획안 I6 :644 는 명단에 응답 여부를, 원칙 10(:247)은 답과의 비연결을 요구한다 | 8 | 명단은 현재 설문의 여부(bool \| null)만, 결과는 집계만, 둘을 잇는 응답 id·제출 시각은 어디에도 없다. 차분 노출 세 경우(관리자 열린 기간 · 강사 재개방 두 스냅샷 · 명단 응답 여부 + 스냅샷)는 1차 정책 "임계 5 + 재개방 허용, 차분은 막지 않음" | T8 결정 xii·xiv 기본 · 대안(재개방 뒤 재공개 금지 · 증가분 임계) 열림 |
| 2026-10-23 | 기획안 L1 :683 은 응답 뒤 배너가 사라진다 하고 학습자 시안 :708 은 「참여 완료」 를 남긴다(MAT-007 :216 글자도 "참여 완료 표시") | 해당 없음 | 기획안대로 응답 뒤 숨김 — 포털 `survey` 칸은 강의 단위이고 화면이 설문 GET 의 `responded` 로 숨긴다 | T8 결정 xv 기본 · 대안 ③(참여 완료 유지) 열림 |
| 2026-10-23 | 시안 관리자.html:1876 `delRound` 는 확정 회차도 지우고 뒤 번호를 당긴다, 요구정의서 DIA-007(:255)·기획안 :832 는 확정 회차 수정 불가 · 삭제는 응답을 받지 않은 것으로 처리 | 해당 없음 | 삭제는 draft·review 만, 번호는 당기지 않는다(마지막 번호는 최대 + 1 로 다시 받는다), 링크 회차를 지우면 그 링크는 revoked | T9a 결정 iv D9 기본 |
| 2026-10-23 | 시안 `buildSectionsFromReco`(관리자.html:1563)는 제목 접두로 풀 과정을 찾아 `courseRef` 를 단다 | 해당 없음 | 개설 ③ 은 권장 구성의 후보 제목 글자만, 풀 참조 없음(강사 미배정) | T9a 결정 vii 기본 · 대안 ② 열림 |
| 2026-10-23 | 시안 `axToken`(관리자.html:1154)은 8자 A-Z2-9, Design 2절은 토큰이 주체 | 해당 없음 | `secrets.token_urlsafe(24)` 32자(192비트) | T9a 결정 vi 기본 |
| 2026-10-23 | r3 309 는 "연결 강의 있으면 삭제 409", 요구정의서 DIA-001(:249)·시안 `delCompany`(관리자.html:1877 `!c.archived`)는 활성 연결 강의만 | 해당 없음 | 활성(`archived_at IS NULL`) 연결 강의만 409, 보관 강의의 연결은 `course.company_id` 가 SET NULL 로 풀린다 | T9a 결정 iii 기본 · 대안 ④(전부 409) 열림 |
| 2026-10-23 | 시안 `axSync`(관리자.html:1171)는 만료된 open 링크를 expired 로 바꿔 발급을 허용하고, r3 337 의 open 부분 유일은 저장 상태만 본다 | 해당 없음 | 발급이 만료된 open 을 먼저 회수(revoked · reason expired)한 뒤 발급 | T9a 결정 vi 기본 · 대안 ①(409) 열림 |

## 4. 스펙 변경 규칙

1. 정본 문서의 버전·상태·변경 이력을 올린다.
2. 같은 커밋에서 1절 색인 행을 갱신한다. 외부 정본(기획안·파이프라인·시안)이 바뀌면 같은 커밋에서 색인의 sha256 을 고친다. pre-push 의 `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` 가 어긋남을 막는다. CI 에는 외부 파일이 없어 `외부 정본 검사 건너뜀` 을 찍는다.
3. 승인은 승인자의 빈 커밋 `approve: T<n>`(트레일러 `Approved-by: DAMIEN-PARK`)이다. 에이전트는 둘 다 쓰지 않는다([agent.md](agent.md) 4절).
4. "함께 바뀌어야 하는 문서" 열의 문서를 같은 변경에서 대조한다.
5. 정책이 바뀌면 2절 끝 문장대로 한다.
6. `scripts/check_docs.sh` 가 읽는 모양을 지킨다.
   - 1절: 머리 행에 `파일`·`위치`·`sha256` 열이 있다. 파일 칸의 첫 백틱 글자가 저장소 루트 기준 경로다. 저장소 문서는 그 글자를 링크로 감싼다. 위치 칸은 `저장소` 또는 `외부` 다. 외부 행의 sha256 칸은 백틱 안의 64자다.
   - 2절: 머리 행에 `어디에 코드로` 로 시작하는 열이 있다. 그 칸은 빈칸·`-`·`—` 이 될 수 없다.
   - Design 부록 A: 머리 행이 `규칙`·`T`·`시험 이름` 열을 가진다. 읽는 법은 그 부록 머리에 있다.




---

# Resources

- SDLC 안내서 `2026-10-06-ai-native-sdlc-porting-guide.md` §5 4단계 관문 · §6.4 spec 틀(저장소 루트)
- 승인된 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` §0 · §2 · §3 · 부록 A2·A3 · E4·E9·E10. r1 `.omc/plans/2026-10-21-classfit-phase1.md` D7. 저장소 루트 기준 경로이고, `.omc/` 는 gitignore 라 git 에 남지 않는다.
