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
| 태스크 순서 | [`docs/process/plan.md`](plan.md) | 저장소 | git 추적 | T0a·T0b 병합 · T1 진행 중 | r3 §5.2 | 태스크 계획 · [agent.md](agent.md) |
| 에이전트 편성 | [`docs/process/agent.md`](agent.md) | 저장소 | git 추적 | 승인자 DAMIEN-PARK | r3 §5.1 · 부록 E11 | CLAUDE.md · `.claude/settings.json` |

## 2. 정책 대조표

r3 §3 원칙 ①~⑤ 와 기획안 03 운영 원칙 중 서버가 지킬 것(2·5·10·12·13)이다. "어디에 코드로 있는가" 칸은 지금 있는 장치를 실제 경로로 적는다. 코드가 아직 없으면 `예정: T<n> + 시험 이름` 으로 적고, 이름은 [Design 부록 A](2026-10-21-phase1-backend-design.md) 대응표의 것을 쓴다.

| # | 정책 | 어디에 코드로 있는가 | 강제·권고 | 소유자 |
|---|---|---|---|---|
| 1 | r3 원칙 ① 계획 먼저, 승인은 사람만 | `.claude/hooks/deny-approval.sh`(에이전트 커밋의 승인 표시 차단) · `scripts/check_task_order.sh`(가지는 plan → approve → T 커밋 순서, master 는 병합 커밋만. pre-push·CI) · `.githooks/pre-commit`(master 직접 커밋 차단) · `.githooks/pre-merge-commit`(스크립트 밖 master 병합 차단) · `.claude/settings.json` deny(병합·push·reset·훅 우회) · `scripts/merge_task.sh`(승인자 전용) · [agent.md](agent.md) 4절 | 강제(훅·CI). 같은 계정의 위조는 기계로 다 막지 못한다 | DAMIEN-PARK |
| 2 | r3 원칙 ② 원본은 한 곳 | 이 문서 1절 + `scripts/check_docs.sh` ①②(색인 경로 실재 · 외부 정본 sha256, pre-push 는 `CLASSFIT_REQUIRE_EXTERNAL=1`) · `src/classfit/main.py`(`/v1/openapi.json`) · `tests/contracts/test_api_openapi.py`(E-13, OpenAPI 경로 집합 = `tests/contracts/expected_paths.txt`, `/v1/_probe` 없음) · 예정: T2a + `test_golden_schedule_`, T9a + `test_golden_score_`(시안 산식과 같은 원본) | 강제(pre-push·CI) | DAMIEN-PARK |
| 3 | r3 원칙 ③ 판정은 서버가, 규칙마다 시험 1개 이상 | [Design 부록 A](2026-10-21-phase1-backend-design.md) 대응표 + `scripts/check_docs.sh` ④(병합된 T 의 행마다 `tests/` 에 def) · `tests/conftest.py`(시험 DB 가 없으면 pytest.fail, skip 금지) · `.claude/hooks/protect-tests.sh`(버그 픽스 모드에서 tests 편집 차단) | 강제(check_docs·CI test) | DAMIEN-PARK |
| 4 | r3 원칙 ④ 지금 대표 데이터로 검증 | `tests/conftest.py`(라이브 Postgres, 세션마다 downgrade base → upgrade head) · `.github/workflows/ci.yml` test 잡(postgres:17) · 예정: T2a + `scripts/golden/extract.mjs` · `test_golden_schedule_` · 예정: T9a + `test_golden_score_`(E-12) | 강제(CI test) | DAMIEN-PARK |
| 5 | r3 원칙 ⑤ 강제는 기계로 | `Makefile` verify(editable-check → gate → lint → lint-imports → test, T0b 에서 끝에 okf) · `.githooks/pre-push` · `.github/workflows/ci.yml` gates·test · 금지 의존성 `pyproject.toml` banned-api(ruff TID251) · `.claude/hooks/deny-deps.sh` · `scripts/gate.sh` · 차단기 회귀 `scripts/test_gate.sh` · `.claude/hooks/test_hooks.sh` · 문서 `scripts/okf/guard.sh`(T0b) · `scripts/check_docs.sh` | 강제(훅·CI) | DAMIEN-PARK |
| 6 | 기획안 원칙 2 수강생의 문은 초대코드 하나(가입·비밀번호 없음) | [ADR-002](adr/ADR-002-learner-session.md) · `tests/integration/test_db_auth_session.py`(수강생 세션은 course_id 필수, auth_session CHECK) · 예정: T2b + `test_p3_*` 9건(E-10) · `test_cross_course_portal_403` | 시험(T1 일부, T2b 예정) + ADR | DAMIEN-PARK |
| 7 | 기획안 원칙 5 첨부가 없거나 공개가 꺼진 세션은 "준비 중" | 예정: T2b + `test_portal_locked_` | 시험(예정) | DAMIEN-PARK |
| 8 | 기획안 원칙 10 응답은 개인과 연결해 보여 주지 않는다 | REVIEW.md 보안 패스(원칙 10 항목) · [Design](2026-10-21-phase1-backend-design.md) 1절 만족도 공개 범위 · 예정: T2b + `test_no_personal_keys_portal` · T4 + `test_no_personal_keys_catalog` · T8 + `test_no_personal_keys_i7`·`test_no_personal_keys_a5`(E-14) | 리뷰 + 시험(예정) | DAMIEN-PARK |
| 9 | 기획안 원칙 12 실제 고객사명은 시안·데모 데이터에 쓰지 않는다 | `scripts/gate.sh` 4번(금지 용어 `scripts/forbidden_terms.txt`, 범위 src·tests·alembic·scripts·docs·루트 md, 출력은 file:line 만) · pre-push·CI 의 `CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1` · `scripts/check_secrets.sh` · CLAUDE.md Rules · 예정: T2a + `scripts/golden/extract.mjs` 가명 토큰 | 강제(CI) | DAMIEN-PARK |
| 10 | 기획안 원칙 13 강의는 관리자가 개설하고 강사를 배정한다. 강사는 구조를 만지지 않는다 | CLAUDE.md Rules 단일 진입점 `open_course()` · 예정: T5 + `test_assign_`(미승인 배정 409) · `test_instructor_session_`(제목 PATCH 422 · 남의 세션 403) | 시험(예정) | DAMIEN-PARK |

정책이 바뀌면 소유자가 정하고, 같은 커밋에서 훅·스크립트·문서를 고치고, 이 표의 행을 갱신한다.

## 3. 우려 사항 처리 기록

r3 부록 A2 데이터 계약 차이 11건, A3 시안 전용 기능 5종, §2 가정 7(기획안 내부 모순), 요구정의서 §10 DEC-001~016 이다. 정책 # 는 2절의 번호다. DEC 행의 원문과 영향은 [요구정의서](../requirements/2026-10-21-요구정의서.md) §10 에 있다.

| 일자 | 우려 | 정책 # | 처리 | 상태 |
|---|---|---|---|---|
| 2026-10-21 | A2-1 Course 칸 이름·값 표기가 시안끼리, 시안과 기획안이 다르다(title·name, client·company, method·mode, 시수, 상태, 날짜 구분자) | 2 | title·client_name·method·hours_per_person(int)·status prep·running·ended, ISO 8601 | 결정(r3) · T2a |
| 2026-10-21 | A2-2 InviteCode 가 기획안은 별도 개체, 관리자 시안은 Course 에 납작, 강사 시안은 객체 | 2 | 별도 표, 재발급 이력은 replaced 행 | 결정(r3) · T2a |
| 2026-10-21 | A2-3 Enrollment 를 관리자는 수만, 강사는 목록으로, 기획안은 이메일로 사람을 묶는다 | 2 | learner(이메일만) + enrollment(이름·부서), 응답 여부는 계산 | 결정(r3, ADR-002) · T2b |
| 2026-10-21 | A2-4 Session·Attachment 칸 이름이 넷(att·files·attachments·keys), 종류 img·image | 2 | keywords[], kind=image, href | 결정(r3) · T2b |
| 2026-10-21 | A2-5 Diagnosis·DiagLink 상태 값이 다르다 | 2 | draft·review·final / open·submitted·revoked, 만료는 계산 | 결정(r3) · T9a |
| 2026-10-21 | A2-6 Company 규모가 시안 5구간, 문의 4구간 | 2 | 회사 5구간, 문의 4구간 그대로 | 결정(r3) · T9a·T9b |
| 2026-10-21 | A2-7 강사 서류가 기획안 3종, 시안 4종 + 계약서 + 기타 | 2 | document_type 표, 시드 3종. 최종 항목은 DEC-006 | 1차 결정(r3) · DEC-006 열림 |
| 2026-10-21 | A2-8 Capability 의 시안 confirmed·fix | 2 | 1차는 기획안대로 | 결정(r3) · T4 |
| 2026-10-21 | A2-9 Pool 직무군이 문자열과 배열로 다르다 | 2 | job_groups[] | 결정(r3) · T4 |
| 2026-10-21 | A2-10 심화 과정 시드에 id·pub·active 가 없다 | 2 | 표에 둔다 | 결정(r3) · T4 |
| 2026-10-21 | A2-11 입장 부서가 강의 섹션과 공통 16 + 직접 입력으로 다르다 | 2 | 기획안대로. 선택지 확정은 DEC-016 | 1차 결정(r3) · DEC-016 열림 |
| 2026-10-21 | A3-1 강사 일정·배정 겹침 알림이 시안에만 있다 | 해당 없음 | 1차 제외, intent 후보로 기록 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-2 시수·월별 정산 확정이 시안에만 있다 | 해당 없음 | 1차 제외. 시수는 교육 기록의 실시 시각으로 나중에 계산 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-3 서류 종류 설정이 시안에만 있다 | 해당 없음 | 종류 표만, 편집 API 는 2차 | 1차 일부 · DEC-015 |
| 2026-10-21 | A3-4 강사위촉계약서가 시안에만 있다 | 해당 없음 | 1차 제외 | 1차 제외 · DEC-015 |
| 2026-10-21 | A3-5 가능 과정 확인·보완 요청이 시안에만 있다 | 해당 없음 | 1차 제외, reviewed 토글만 | 1차 제외 · DEC-015 |
| 2026-10-21 | 가정 7 기획안 내부 모순: 과정 풀 절 "DB에는 고유 과정과 가능 표시만" ↔ 원칙 6, 고유 과정 "삭제" ↔ 파이프라인 9 "삭제 없음" | 2 | AX 과정도 DB 원본, 고유 과정 삭제는 사용 중지, 패키지명 classfit 유지 | 결정(r3 §2 가정 7) |
| 2026-10-21 | DEC-001 만족도 100점 환산식이 관리자·강사 시안에서 다르다 | 2 | 단일 환산식 선택 권고, 긍정률은 실제 4·5점 비율 | 결정 필요 |
| 2026-10-21 | DEC-002 관리자 일정과 강사·학습자 시간 함수의 점심·요일 처리가 다르다 | 2 | 관리자 일정 정의로 통합 권고, 시수 기준 확정 | 결정 필요 |
| 2026-10-21 | DEC-003 진단 17지표 최저 응답 총점 160 이라 L1 이 불가능하다 | 2 | 단계 점수 체계·레벨 경계를 기획자가 확정, 임의 변경 금지 | 결정 필요 |
| 2026-10-21 | DEC-004 학습자 시안은 강의를 즉시 전환하고 전역 이름을 쓴다 | 6 | ADR-002 로 결정됨. 시안 UI 수정 대상 | 결정(ADR-002) |
| 2026-10-21 | DEC-005 강사 반려·정지 제한, 재신청, 관리자 초기 비밀번호가 시안에서 미완성 | 해당 없음 | 공개홈·기존 설계와 대조해 인증·복구·정지 범위 확정 | 결정 필요 |
| 2026-10-21 | DEC-006 필수 서류가 시안 4종 + 계약서, r3 는 기획안 3종 시드 | 해당 없음 | 초기 제출 항목·예외·필수 정책 확정. 1차 시드는 3종(r3 §7-2) | 결정 필요 |
| 2026-10-21 | DEC-007 실제 시각 공란이면 계획 시간으로 집계, 확정 후 수정 흐름이 불분명 | 해당 없음 | 실제 시간 필수 여부·수정 이력 확정. 정산은 1차 제외 | 결정 필요 |
| 2026-10-21 | DEC-008 보관 강의를 관리자 시수 집계에서 뺀다 | 해당 없음 | 역사적 집계 유지 권고, 보관 후 규칙 확정 | 결정 필요 |
| 2026-10-21 | DEC-009 비공개 차시 숨김 안내와 학습자 렌더러 판정이 다르다 | 7 | 비공개 카드 숨김·노출 범위 확정. 자료 접근 차단은 공통 | 결정 필요 |
| 2026-10-21 | DEC-010 강의안·서류 크기 검증과 교체 UI·HTML 구성이 미정 | 해당 없음 | 확장자·MIME·크기·교체 방식 확정. 1차 상한은 기획안 I4 | 결정 필요 |
| 2026-10-21 | DEC-011 1차는 outbox·501, 시안은 발송·열기·PDF 를 표현 | 해당 없음 | ADR-003 의 1차 제한은 결정됨. 업체·재시도·뷰어·출처는 후속 | 1차 결정(ADR-003) · 후속 열림 |
| 2026-10-21 | DEC-012 양식 자유 편집과 학습자·결과 렌더러의 고정 문항이 다르다 | 해당 없음 | 배포 복제본 기준 동적 입력·집계 권고, 수정 범위 확정 | 결정 필요 |
| 2026-10-21 | DEC-013 설문 분모·결측·강사 결과 공개 시점·최소 응답 수가 불충분 | 8 | I7 최소 5건은 제안값(Design 1절). 공개·소수 응답 정책 확정 | 결정 필요 |
| 2026-10-21 | DEC-014 성능·보존 기간·브라우저·백업 기준이 없다 | 해당 없음 | 운영 규모·보존·파기 정책 확정. 사진 동의는 별도(r3 §7-6·7) | 결정 필요 |
| 2026-10-21 | DEC-015 시안 전용 5종이 시안에는 있고 r3 1차에서 빠졌다 | 해당 없음 | 시안 전체 요구로 유지. 착수 때 범위 변경 또는 후속 배치 결정 | 결정 필요 |
| 2026-10-21 | DEC-016 과정 시안 데이터가 144개 중 42개 예시, 부서 선택지 코드가 다르다 | 2 | 이관 원본·개수·ID 와 입장 부서 선택지 확정 | 결정 필요 |

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
