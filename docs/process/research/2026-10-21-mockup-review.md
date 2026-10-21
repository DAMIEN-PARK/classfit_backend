---
type: Research
title: "Research: 시안 3종 검토 — 화면·데이터 계약·서버 판정"
description: 관리자·강사·학습자 시안 HTML 3종에서 화면 27개와 API·태스크 대응, 기획안과의 데이터 계약 차이 11건, 시안 전용 기능 5종, 서버 판정 규칙, 공개홈이 빠지며 끊기는 지점을 정리한 검토 기록
date: 2026-10-21
tags: [research, classfit, mockup, api, data-contract]
Archives: false
URL: ""
---

# Research: 시안 3종 검토 — 화면·데이터 계약·서버 판정

- 출처: 승인된 r3 플랜 부록 A1~A5(2026-10-21). 시안 HTML 처리 옵션(부록 A6)은 [ADR-001](../adr/ADR-001-mockups.md) 로 옮겼다.
- 대상: `시안/관리자.html` · `시안/강사.html` · `시안/학습자.html`(미추적, 참고 자료). 검토한 판의 sha256 은 [spec.md](../spec.md) 1절 색인에 있다. 아래 `파일:줄` 은 그 판의 줄 번호다.
- 읽은 범위(r3 부록 H): 상수·함수 목록 전체, 라우터(강사.html:1305 · 관리자.html:2209 · 학습자.html:913), 사이드바(강사.html:866 · 관리자.html:1131), 시드·규칙 발췌. 기획안 v3 · 파이프라인 v3 추출본은 전부 읽었다.
- 이 기록은 결정이 아니다. 결정은 [Design](../2026-10-21-phase1-backend-design.md) 과 ADR 에 있다. 시안 전체의 요구 목록은 [요구정의서](../../requirements/2026-10-21-요구정의서.md)(검토용)에 있다.

## A1. 화면 ↔ 데이터 ↔ API ↔ 태스크

시안 3종에서 화면 27개를 뽑았다. API 경로는 예정이고, 정본은 `/v1/openapi.json` 이다.

| 화면 | 시안 위치 | 읽기 | 쓰기 | 1차 API | T |
|---|---|---|---|---|---|
| A0 로그인 | 관리자.html:1314 | Admin | 세션 | `POST /v1/auth/admin/login` | T1 |
| A3 강의 목록·개설(빈 강의)·편집·일정표·코드 관리 | 관리자.html:1445, 1584, 1713, 1792 | Course·Day·Section·Session | 같은 것·InviteCode | `/v1/admin/courses…` | T2a (시작점 ②④ T5, ③ T9a) |
| 재입장 = P3 | 학습자.html:627 | InviteCode·Course | Learner·Enrollment | `/v1/enter/lookup`, `/v1/enter` | T2b |
| L1 포털 · L2 강의안 | 학습자.html:704, 753, 786 | Course·Day·Section·Session·Attachment | 없음 | `/v1/learner/courses/{id}/portal`, 응답의 `href` | T2b |
| I2 프로필·서류 | 강사.html:918, 622 | Instructor·Tag·Document | 같은 것 | `/v1/me`, `/v1/me/documents/{type}` | T3 |
| A2 강사 관리 | 관리자.html:1346 | Instructor·Capability·Document | status·memo | `/v1/admin/instructors…` | T3 |
| I3 내 과정 | 강사.html:975 | Pool·Capability·OwnCourse·Curriculum | 같은 것 | `/v1/pool`, `/v1/me/{capabilities,own-courses,curricula}` | T4 |
| A3 과정 풀 | 관리자.html:1502 | Pool·Curriculum·심화·Capability | pub·active·reviewed | `/v1/admin/{pool,curricula,advanced-courses}` | T4 |
| A3 배정 · I3-1 구성·일정표 | 관리자.html:1713 · 강사.html:1082, 1060 | Session·Capability | 배정·설명·키워드·공개 | `…:assign`, `/v1/me/courses/{id}` | T5 |
| I4 첨부 · I1 홈 · I5 코드 · I6 수강생 | 강사.html:1114, 893, 1141, 1164 | Session·Attachment·InviteCode·Enrollment | Attachment | `/v1/me/sessions/{id}/attachments`, `/v1/me/home` | T6 |
| 진행 기록 · A3 교육 기록 · A3-2 사진 | 강사.html:1067 · 관리자.html:1799, 2178 | Record·Photo | 같은 것 | `/v1/{me,admin}/…/record`, `/v1/admin/photos` | T7 |
| A5 · L3 · I7 | 관리자.html:2017, 2065, 2080 · 학습자.html:863 · 강사.html:1174 | Template·Survey·응답 집계 | Template·Survey·Response | `/v1/admin/surveys…`, `/v1/learner/courses/{id}/survey` | T8 |
| A4 사전진단 | 관리자.html:1849, 1879, 1902, 1964, 1178 | Company·Diagnosis·DiagLink | 같은 것 | `/v1/admin/{companies,diagnoses,links}`, `/v1/ax/{token}` | T9a |
| A1 관리자 홈 | 관리자.html:1323 | 집계 | 없음 | `GET /v1/admin/home` | T9b |
| A6 설정 | 관리자.html:2106, 2127, 2153 | Tag·DocumentType·Admin | 같은 것 | `/v1/admin/{tags,admins}` | T1·T3 |
| 시안 전용 화면 | 강사.html:1235, 1257, 1289 · 관리자.html:1265, 1292 | — | — | 배정 강의 목록만 `/v1/me/courses` | — |
| 공개홈 P2~P6 (화면 보류) | 루트 `공개홈_v24.html` | A5 표 | A5 표 | P3 T2b · P4 T3 · P2 질의 함수 T4 · P5 T9a · P6 T9b | — |

## A2. 데이터 계약 차이 (기획안 7절·파이프라인 7절 ↔ 시안)

| # | 개체 | 차이 | API 처리 |
|---|---|---|---|
| 1 | Course | `title`(관리자.html:956) ↔ `name`(강사.html:733), `client` ↔ `company`, `method` ↔ `mode`, `16` ↔ `'1인 16시간'`, `run` ↔ `'running'`(학습자.html:459), 날짜 `.` ↔ `-` | `title·client_name·method·hours_per_person(int)·status prep·running·ended`, ISO 8601 |
| 2 | InviteCode | 기획안 별도 개체 ↔ 관리자 Course 에 납작(관리자.html:956) ↔ 강사 객체(강사.html:735) | 별도 표, 재발급 이력은 replaced 행 |
| 3 | Enrollment | 관리자 수만, 강사 목록, 기획안 이메일로 사람 묶음 | learner(이메일만) + enrollment(이름·부서), 응답 여부는 계산 |
| 4 | Session·Attachment | `att`·`files[]`·`attachments[]`·`keys`, 종류 `img`(강사.html:831) ↔ `image` | `keywords[]`, `kind=image`, `href` |
| 5 | Diagnosis·DiagLink | 작성중·검토대기·확정 ↔ `draft·submitted·final`, 링크 `open·used·revoked`(관리자.html:1050, 1161) | `draft·review·final` / `open·submitted·revoked`, 만료는 계산 |
| 6 | Company 규모 | 시안 5구간(관리자.html:1057) ↔ 문의 4구간 | 회사 5구간, 문의 4구간 그대로 |
| 7 | 강사 서류 | 기획안 고정 3종 ↔ 시안 4종 + 계약서 + 기타(강사.html:552) | `document_type` 표, 시드 3종 |
| 8 | Capability | 시안 `confirmed·fix`(관리자.html:1213) | 1차는 기획안대로 |
| 9 | Pool 직무군 | `deptName` 문자열(관리자.html:857) ↔ `depts[]`(강사.html:689) | `job_groups[]` |
| 10 | 심화 과정 | 시드에 id·pub·active 없음(관리자.html:912) | 표에 둔다 |
| 11 | 입장 부서 | 강의 섹션(학습자.html:675) ↔ 공통 16 + 직접 입력(기획안 P3) | 기획안 |

## A3. 시안에만 있는 기능 (기획안 12절 "10/16 판과 같다"와 어긋남)

| 기능 | 시안 위치 | 1차 |
|---|---|---|
| 강사 일정·배정 겹침 알림 | 강사.html:1241-1286 · 관리자.html:1203, 1230-1237 | 제외, intent 후보로 기록 |
| 시수·월별 정산 확정 | 강사.html:1289 · 관리자.html:1292-1312 | 제외. 시수는 Record 의 실시 시각으로 계산되므로 표를 더하지 않고 붙일 수 있다 |
| 서류 종류 설정 | 강사.html:552-620 · 관리자.html:2127 | 종류 표만, 편집 API 는 2차 |
| 강사위촉계약서 | 강사.html:557, 636 | 제외 |
| 가능 과정 확인·보완 요청 | 관리자.html:1212-1218 · 강사.html:855-857, 1011 | 제외, reviewed 토글만 |

1차 범위 결정은 [feature intent](../intents/2026-10-21-phase1-backend.md) "1차에서 명시적으로 빼는 것"에 있다.

## A4. 서버가 판정해야 하는 것

이 표는 [Design](../2026-10-21-phase1-backend-design.md) 부록 A "규칙 ↔ 시험 이름 대응표"의 출처다.

| 규칙 | 시안 | 서버 | T |
|---|---|---|---|
| 코드 생성 | `genCode`(관리자.html:1417) | 같은 알파벳, 전 행 유일 | T2a |
| 세션 시각·일정 | `scTime`·`scMakeDays`(관리자.html:665, 675) | 순수 함수, golden | T2a |
| 강의 상태·종료 시 코드 정지 | 수동 토글 | `course_status_at` + SQL 판, `code_state_at` | T2a |
| 초대코드 검증(입장) | 상수 + 종료 토글(학습자.html:669) | 코드 상태 + 강의 상태, 기획안 P3 표 7행 | T2b |
| 파일 접근 | 없음 | 범위 판정 → 바이트, 미등록 종류 404, 응답은 `href` | T1·T2b |
| 준비 중 카드 | 화면 계산 | `is_open` ∧ 첨부 ≥1 | T2b |
| 기본 강의안 자동 첨부 | 목록 복사 | 행 복제, 바이트 공유 | T5 |
| 기록 상태 | `SC_REC` | none → done → ok, 확인 뒤 수정 → done | T7 |
| 1인 1회·문항 잠금·열린 설문 1개 | 상수 | 유일 제약·FOR UPDATE·409 | T8 |
| 응답 비연결 | 화면 | I7·A5 모두 개인 키 없음, I7 최소 응답 수 | T8 |
| 진단 점수 | `calc`(관리자.html:1037) | 같은 산식, golden | T9a |
| 진단 링크 | `axIssue`(관리자.html:1161) | 회사당 open 1, 제출 즉시 닫힘 | T9a |
| 메일·인증 코드 | 토스트, 123456 고정 | outbox kind + params, 코드는 `issue_email_code()` 에서만 생성 | T1·T3 |

## A5. 공개홈이 빠지면서 끊기는 지점 (API 는 만들고 화면은 보류)

| 화면 | 남은 시안 | 막히는 것 | 처리 |
|---|---|---|---|
| P3 입장 | 학습자.html `#enter`(627) | 화면은 대체됨. 준비 중·만료·정지·정원 분기 없음 | T2b API, 이유는 problem type 으로 구분 |
| P4 강사 로그인·가입 | 없음, 로그아웃이 `공개홈_v24.html#login`(강사.html:867) | 파이프라인 6 입구 | T3 API |
| P5 자가진단 응답 | 없음, 링크가 `공개홈_v24.html#ax/{token}`(관리자.html:1156) | 자가 갈래 | T9a 토큰 API |
| P6 교육 문의 | 없음 | 제안 0단계, 다른 흐름 영향 없음 | T9b 접수 API, 발송은 요청 제한 뒤 |
| P2 카탈로그 | 없음 | 공개 읽기만 없음 | T4 질의 함수 + 통합 시험, 끝점은 H-1 뒤 |

이 표의 처리는 [ADR-004](../adr/ADR-004-public-home.md) 로 결정했다. H-1 은 r3 §7 1번 질문(공개홈을 왜 루트로 옮겼는가)이다.




---

# Resources

- 승인된 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` 부록 A1~A5 · 부록 H. 저장소 루트 기준 경로이고, `.omc/` 는 gitignore 라 git 에 남지 않는다.
- 시안 `시안/관리자.html` · `시안/강사.html` · `시안/학습자.html`, 공개홈 `공개홈_v24.html`(모두 미추적, 저장소 루트 기준)
