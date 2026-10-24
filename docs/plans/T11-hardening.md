---
type: Task Plan
title: "Plan: T11 hardening"
description: 1차가 남긴 엔지니어링 후보를 묶은 경화 태스크 계획 — 전역 본문 상한(인증 전 413), 토큰이 실리는 응답의 no-store, 요청 로그 토큰 가림, 정수 경로 매개변수 상한, 업로드 길이 검사 공용화, 관리자 92연산 강사 403 시험, 운영자 미리 보기 제어 문자 이스케이프, inquiry_gc 배열 바인드, 0012(설문 양식 색인 · 공백류 CHECK), ruff format 관문, T10 P4 문서와 2차 입력 목록
date: 2026-10-24
tags: [plan, task, t11, hardening, security, migration, tooling, classfit]
Archives: false
URL: ""
---

# Plan: T11 hardening (from plan.md#T11, 2026-10-24)

- **계획 4판.** 3판의 codex 계획 2차(BLOCK — 1차 11건 중 9 CLOSED, #2 · #11 NOT CLOSED, 새 중대 1 · 경미 1)를 반영했다: CORS preflight 는 상한 약속 밖(#2) · `Match.FULL` 만 업로드(#1 보강) · 안내문 응답 둘을 입장 코드 대안에(#11) · 마이그레이션 시험 정리 순서(행 지우기 → 연결 닫기 → `upgrade head` 성공 단언, 새 1) · 구조 시험 허용 목록을 함수 객체로(새 2).
- **계획 3판.** 2판의 verifier 좁은 확인(FAIL — 차단 3 · 권고 7 · nit 12, 수치·인용은 전부 MATCH)을 반영했다: 하한 상수 글자 통일(B1) · 증명 grep 기대값(B2) · `IdPath` 사용처 열 곳(B3) · FastAPI 줄 번호와 400/500 구분(R1) · 행 가드 전례 0005 `GUARD`(R2) · 강사 403 은 새 시험(R3) · CORS 단언은 시험용 앱(R4) · 계획 글의 보이지 않는 글자 셋을 이스케이프 글자로(R5) · Starlette 내장 상한을 안 쓰는 이유(R6) · 구조 시험 허용 목록은 이름 글자(R7) · nit 12. verifier 실측: 읽은 바이트 413 이 pydantic 본문 · Form · 핸들러 안 `request.form()` · `limited_json` 네 길 모두 problem 413 · 미들웨어 순서 바깥 → 안 RequestLog · GZip · CORS · BodyLimit 에서 두 갈래 413 에 CORS 헤더와 요청 기록이 남는다 · 업로드 라우트 8 이 `matches(scope)` 로 하나씩 맞는다.
- **계획 2판.** 1판(248줄)의 codex 계획 1차(BLOCK — 차단 1 · 중대 8 · 경미 2)를 반영했다: 본문 상한을 라우트로 고름(#1) · 선언 길이/읽은 바이트 두 갈래와 http 밖 scope(#2) · 업로드 갈래 시험을 시험용 설정으로(#3) · `no_store` 순서 허용과 하한 92(#4) · BMP 밖 서식 문자 서로게이트 쌍(#5) · 배열 타입 셋(#6) · `file_gc` 임시 파일은 T11 에서 뺌(#7) · 데이터 있는 0011 → 0012 와 왕복·모델 일치 시험(#8) · 요청 기록 32자 이상 줄 가림(#9) · 시험 전제(#10) · 입장 코드 목록(#11).
- 근거: 1차 태스크 계획들의 "리뷰"·"계획과 다르게 한 것" 절에 남은 승인자 판단 후보(T1 :241·:243 · T2b :279 · T3 :263·:309 · T4 :280-281 · T5 :414 · T6 :388 · T7 :424 · T8 :449-453 · T9a :527-533 · T9b :471-475) · T10 계획 P4(병합 뒤 ④ · plan.md T10 행 · spec :38) · Design 5절 :106("일반 적용은 열린 것"). 승인자 지시(2026-10-24): "남은것 진행해 codex 리뷰도 같이" — 계획과 구현 둘 다 codex 리뷰를 거친다.
- 승인: (리드가 승인 요청 뒤 채운다 — 승인의 증거는 approve 커밋이다.)
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T11" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.
- 가지: `T11-hardening` 을 master `4c32046 merge: T10 phase1-close` 에서 땄다.
- 범위: 제품 결정이 필요 없는 엔지니어링 수정만. 새 끝점·새 응답 칸·새 의존성은 없다. 제품 결정이 필요한 후보는 고치지 않고 plan.md 4절 "2차 입력" 목록으로 옮긴다(결정 xvii).
- 표기: 〔정함〕은 정본(Design·r3·요구정의서·시안)에 없는 이름·값을 이 계획이 정했다는 뜻이다.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T10 병합 | 충족 — master `4c32046 merge: T10 phase1-close`(트리 = T10 가지 머리 `44f5a82`) · push 됨 · 병합 커밋 CI success(run 40083200691) · 병합 뒤 `check_docs.sh` ④ `T0a T0b T1 T10 T2a … T9b · 대응표 48행 중 대상 48행` | T10 계획 P4 |
| 새 의존성 | 없다(FastAPI·Starlette·SQLAlchemy·ruff 는 이미 있는 판) | requirements*.txt |
| 마이그레이션 | **0012** 하나(결정 xii): `survey.template_id` 색인 + 공백류 CHECK 여섯을 다시 만든다. head 는 `0012 (head)` 가 된다 | Design 4절 |
| 기준 수(`4c32046`) | `make verify` 558 passed · expected_paths 125(T11 은 경로를 더하지 않는다) · 관리자 연산 92 · 본문을 받는 연산 64(JSON 56 = pydantic 본문 54 + `limited_json` 2 · multipart 8) · 인증 없는 JSON 연산 8 · 정수 경로 매개변수에 상한이 없는 연산 39(매개변수 44) · 강사 토큰 403 시험이 있는 관리자 연산 12/92 · `ruff format --check` 다른 파일 36(.py 35 + 루트 md 1) | 리드 사실 조사 셋(2026-10-24, 읽기 전용 — 아래 각 결정에 인용) |
| 기본값으로 진행하는 결정 | 승인자가 approve 전에 바꾸라고 하지 않으면 아래 (i)~(xvii) 기본값대로 간다. 승인자 질문은 ①~⑦(이 절 끝) | — |

## 결정 (기본 / 대안)

- **(i) 전역 본문 상한 — 인증 전에 413. 승인자 질문 ①.**
  - 사실: pydantic 본문 매개변수 연산 54개는 의존성(인증)을 풀기 전에 `await request.body()` 로 본문 전체를 메모리에 읽는다(`.venv/…/fastapi/routing.py:455-475` → 의존성 `fastapi/dependencies/utils.py:648`). 실측: 5,000,001 바이트를 Authorization 없이 `POST /v1/admin/admins` 에 보내면 다 읽은 뒤 422 다. 칸의 `max_length` 는 파싱 뒤에만 걸려 바이트 상한이 아니다. 지금 바이트 상한은 `limited_json` 두 곳(`app/endpoints/inquiries.py:41` 64KiB · `app/endpoints/survey_learner.py:108` 256KiB)뿐이다.
  - 기본: 순수 ASGI 미들웨어 `BodyLimitMiddleware` 〔정함〕(`app/middleware.py`). **상한은 Content-Type 이 아니라 라우트로 고른다**(codex 계획 1차 #1 — JSON 끝점은 Content-Type 을 보기 전에 본문을 다 읽으므로 `fastapi/routing.py:458`, multipart 라고만 붙이면 큰 상한을 얻는 우회가 생긴다). 업로드 연산 = `ROUTERS` 의 APIRoute 중 `openapi_extra` requestBody 에 `multipart/form-data` 가 있는 것(지금 8 — attachments.py:60 · instructor_documents.py:52 · my_attachments.py:72 · photos.py:60 · pool_files.py:64 가 선언)이고, `install_middleware` 가 앱을 만들 때 한 번 모아(라우터를 더하기 전에 불리므로 `main.py` — `app.routes` 가 아니라 `ROUTERS` 를 import 한다, 계약에 걸리지 않음) 요청의 method·path 를 그 라우트의 `matches(scope)` 가 `Match.FULL` 일 때만 업로드로 판정한다(`starlette/routing.py:258` — PARTIAL 은 경로만 맞고 메서드가 다른 경우). 업로드 연산의 상한 = (업로드 상한 설정 다섯 `attachment_pdf/office/zip/image_max_mb`·`document_pdf_max_mb` 중 가장 큰 값 + 2) MiB(기본 102MiB — 끝점 `_check_length` 의 `max_bytes + MIB` 보다 커서 끝점 413 이 먼저 난다), **그 밖의 모든 요청은 Content-Type 과 상관없이 1MiB** 〔정함〕.
  - 두 갈래(codex 계획 1차 #2): ① **선언 길이** — `Content-Length` 가 ASCII 숫자이고 상한을 넘으면 앱을 부르지 않고(인증 전) problem+json 413(`/problems/content-too-large`, detail `본문이 너무 큽니다(<n>바이트까지)`)을 보낸다. 본문을 읽지 않는 GET·HEAD 도 같다. ② **읽은 바이트** — 그 밖이면 receive 를 감싸 `http.request` 본문 바이트를 세고 상한을 넘는 청크에서 Starlette `HTTPException(413)` 을 던진다. 이 갈래는 무언가 본문을 읽을 때만 돈다 — pydantic 본문 연산은 인증 전에 읽고, 업로드 연산은 인증·`_check_length` 뒤 `request.form()` 에서 읽고, `limited_json` 은 415 를 먼저 본다. FastAPI 본문 읽기는 `HTTPException` 을 그대로 다시 던지고(`fastapi/routing.py:492-494` — 다른 예외형은 FastAPI 가 본문을 읽는 본문·Form 매개변수 연산에서 400 `:495-499`, 핸들러 안 `request.form()`·`limited_json` 에서 500 — verifier 실측) Starlette 폼 파서도 파일을 닫고 다시 던져(`starlette/formparsers.py:297`) `app/errors.py::_http_error`(:190) 가 problem 으로 바꾼다(구현 첫 단계 a3 에서 두 길 다 실측). `http.disconnect` 는 세지 않고 그대로 넘긴다. scope type 이 `http` 가 아니면(websocket·lifespan) 손대지 않는다. CORS 가 가로채 바로 답하는 preflight(`OPTIONS` + `Access-Control-Request-Method`, `starlette/middleware/cors.py:86`)는 BodyLimit 에 닿지 않는다 — 본문을 읽지 않는 응답이라 상한 약속에서 뺀다(codex 계획 2차 #2). 빈 본문은 그대로 지난다. 쌓는 자리는 CORS 안쪽(413 에도 CORS 헤더가 붙게) · 요청 기록 안쪽(413 도 기록된다).
  - 판정 순서: 선언 길이 413 은 CORS preflight 를 뺀 모든 판정(401·403·411·415·422)보다 먼저다. 읽은 바이트 413 은 그 연산이 본문을 읽는 자리의 순서를 따른다. 상한 안의 요청은 지금과 같다 — `limited_json` 두 끝점의 64KiB·256KiB 와 415, 업로드 끝점의 411·413 은 그대로다.
  - Starlette 1.9.0 의 `RequestBodyLimitMiddleware`(`starlette/middleware/body_limit.py`)를 쓰지 않는 이유: 413 이 평문이라 problem+json 규칙(`app/errors.py`)에 어긋나고(:93·:119), FastAPI 의 `build_middleware_stack`(`fastapi/applications.py:1032-1083`)은 Starlette 의 `max_body_size`(`starlette/applications.py:75-76`)를 무시하며, 라우트별 상한 장치도 없다(`fastapi/routing.py` 에 `max_body_size` 0건) — verifier R6.
  - 대안 a: 인증 없는 JSON 8연산(로그인 둘 · `/v1/enter/lookup` · `/v1/enter` · `/v1/instructors/email-codes` · `/v1/instructors` · `/v1/ax/{token}` · 이미 있는 `/v1/inquiries`)을 `limited_json` 으로 바꾼다 — OpenAPI requestBody 가 인라인이 되고(AxSubmitIn 은 `$defs` 가 생긴다) 경로 매개변수 없는 다섯은 자동 422 응답 선언이 사라지며, 인증이 붙은 54연산은 덮지 못한다. 대안 b: 기본 + 대안 a.
  - 1MiB 근거: 실사용 꼴 본문 중 가장 큰 것은 수 KB 다(구현 첫 단계에서 모델마다 칸 상한을 다 채운 이론 최대 바이트를 재 기록 칸에 적는다 — 이론 최대가 1MiB 를 넘는 모델이 있으면 그 이름을 적고 승인자 질문 ① 의 값 대안으로 올린다).
- **(ii) 토큰 전체가 실리는 응답에 `Cache-Control: no-store`. 승인자 질문 ⑦.**
  - 사실: 응답 모델 중 토큰 전체를 싣는 것은 `LinkOut.token`(`schemas/company.py:112-116`) · `CompanyDetailOut.links`(:132-136) · `TokenOut.access_token`(`schemas/auth.py:30-32`) · `EnterOut.access_token`(`schemas/enter.py:86-88`)이다. 토큰 경로 네임스페이스(revoke)만 미들웨어가 no-store 를 단다(`app/middleware.py:37·43-44`).
  - 기본: `app/deps.py` 에 의존성 `no_store(response: Response)` 〔정함〕를 두고 여섯 연산에 `dependencies=[Depends(no_store)]` — `GET`·`PATCH /v1/admin/companies/{company_id}`(`companies.py:147·155`) · `POST …/links`(:216) · `POST /v1/auth/admin/login`·`/v1/auth/instructor/login`(`auth.py:24·54`) · `POST /v1/enter`(`enter.py:111`). FastAPI 는 핸들러가 모델을 돌려줄 때만 의존성 Response 헤더를 합치므로(`fastapi/routing.py:790`) 오류 응답(problem JSONResponse)에는 붙지 않는다 — 그 경로의 404 에 cache-control 이 없다는 기존 단언 `tests/contracts/test_api_ax.py:500-502` 는 그대로다.
  - 대안: 입장 코드(6자)를 싣는 응답까지 — `InviteCodeOut.code` 를 돌려주는 `invite_codes.py:23·33·53·70·87`(재개 포함) · 개설 `courses.py:139` · 강사 강의 보기 `my_course_views.py:54·63` · 강사 홈 `schemas/my_home.py:44` · 코드가 글자에 들어가는 안내문 응답 둘 `invite_codes.py:104`·`my_course_views.py:75`(본문 `service/courses/codes.py:107` — codex 계획 1차 #11 · 2차 #11). 미들웨어 경로 규칙은 404·422 에도 붙어 위 단언을 깨므로 쓰지 않는다.
  - `no_store` 는 데코레이터 `dependencies=` 라 서명 의존성보다 먼저 돈다(`fastapi/routing.py:915`) — 응답 헤더만 다는 의존성이라 순서는 상관없고, 결정 vi 구조 시험 ④ 가 이것을 허용 목록에 둔다(codex 계획 1차 #4).
- **(iii) 요청 로그의 토큰 값 모양 가림.**
  - 사실: `/v1/%2e/ax/<토큰>` · `/v1/x/../ax/<토큰>` · `/v1/admin/./links/<토큰>:revoke` 는 `TOKEN_PATH_RE`(`app/errors.py:30`)에 안 맞아 요청 기록(`app/middleware.py:55`, 로거 `classfit.request`)에 토큰이 그대로 남는다. 그 로거에는 필터가 없다(실측 `[]` — `TokenRedactFilter` 는 `classfit.errors`·`uvicorn.error` 에만, `errors.py:87-88·219-224`). httpx 는 `/./`·`/../` 는 보내기 전에 지우고 `%2e` 는 그대로 보내, 계약 시험으로 재현되는 것은 `%2e` 꼴이다.
  - 기본(codex 계획 1차 #9 — 33자 이상 줄도 T11 에서 막는다): 요청 기록의 경로는 `request_path(scope)` 뒤에 **`mask_runs`(토큰 글자 32자 이상 줄 → `{token}`, `errors.py:57-59`)를 모든 경로에** 건다 — 토큰 앞뒤에 글자를 붙인 꼴(`…/<토큰>x` · `x<토큰>`)도 가린다. 더해 `classfit.request` 로거에 `TokenRedactFilter` 를 건다(인자 포맷 뒤 값 모양 가림 — `errors.py:75`). 대가: 32자 이상인 풀 과정 id(`POOL_ID_MAX = 80`, `models/pool.py:61`)도 요청 기록에서는 `{token}` 으로 보인다(로그만 — 응답·DB 는 그대로). 응답 `instance` 와 no-store 판정은 그대로다(요청자 본인에게 돌아가는 404 — 2차 입력 목록).
- **(iv) 정수 경로 매개변수 상한 — 공용 `IdPath`·`DayPath`.**
  - 사실: 39연산 44매개변수(id 42 + `day_no` 2)가 `int` 그대로라 2**63 이 DB 까지 가서 DataError 500 이다(T5 :414). T5 가 만든 `IdPath = Annotated[int, Path(ge=1, lt=DB_ID_LIMIT)]`(`app/endpoints/assign.py:42`)와 T7 `DayPath`(`records.py:46`, 1..60)는 그 모듈 안에만 있다.
  - 기본: 둘을 `app/deps.py` 로 옮기고 모든 정수 경로 매개변수에 붙인다(courses·schedule·invite_codes·portal·attachments·enrollments·instructor_documents·admin_instructors·tags·pool_files 와 기존 사용처). 밖의 값은 자원 질의에 닿지 않고 422 `loc ["path", <이름>]` 다 — 인증 질의는 그 전에 돈다(의존성이 경로 검증보다 먼저 `fastapi/dependencies/utils.py:648` vs `:710`, codex 계획 1차 #10). OpenAPI 매개변수 스키마에 `minimum`·`exclusiveMaximum`(DayPath 는 `maximum` 60)이 생긴다(경로 집합은 같다). `day_no` 를 받는 연산은 전부 1..60 일차(schedule `days/{day_no}` 둘 · records)라 DayPath 가 맞다 — 구현 때 경로마다 다시 본다.
- **(v) 업로드 공용 도우미 — 길이 검사 비ASCII · 413 안내문.**
  - 사실: `_check_length`(`app/endpoints/attachments.py:98-104`)는 `raw.strip().isdigit()` 만 봐서 `"²"` 같은 숫자 꼴 비ASCII 가 `int()` 에서 ValueError → 500 이다(T8 이 `deps.py:135` 만 고침). 안내문은 `limit // MIB` 라 끝점이 넘기는 `max_bytes + MIB` 때문에 "51MiB" 로 나온다(T2b :279). `MIB`·`_check_length`·`_invalid` 를 `instructor_documents.py:30`·`pool_files.py:30`·`my_attachments.py:36`·`photos.py:33` 이 비공개 이름으로 들여 쓴다(T3 :263·:309 · T4 :280-281).
  - 기본: 새 모듈 `app/upload.py` 〔정함〕에 `MIB` · `check_length(request, max_bytes)`(ASCII 숫자만 · 안내문은 `max_bytes` 의 MiB · 여유 1MiB 는 안에서 더함) · `invalid(field, msg)` 를 두고 업로드 여섯 자리(attachments:165 · pool_files:124 · photos:148 · instructor_documents:114 · my_attachments:210·:301)가 쓴다. 동작 변화는 비ASCII 길이 411 과 안내문 숫자뿐이다.
- **(vi) 관리자 92연산 강사 토큰 403 시험 + 구조 시험.**
  - 사실: 수강생 403 · 토큰 없음 401 은 `tests/contracts/test_api_admin_guard.py:31-48` 이 92연산 전부를 돌지만, 강사 토큰 403 은 12연산뿐이다. 하한 상수 `T2A_ADMIN_OPERATIONS = 25`(:17)는 낡았다. DB 없이 위조 주체로 잰 결과는 92/92 → 403 이라 코드 결함은 없고 시험이 비었다.
  - 기본: 같은 파일에 새 시험 `test_admin_paths_instructor_403`(같은 OpenAPI 연산 루프)을 두고 `instructor_headers(db_session, 1)`(`tests/fixtures/instructors.py:68`)로 403 `/problems/forbidden` 을 더한다. 구조 시험 하나를 더한다 — `ROUTERS`(`app/routers.py:42`)의 APIRoute 를 돌며(FastAPI 0.156.5 의 `app.routes` 는 `_IncludedRouter` 36 + openapi `Route` 1 을 돌려준다) ① `/v1/admin` 아래는 의존성 트리에 `require_admin` 이 있다 ② 밖에는 없다 ③ 관리자 라우트에 `include_in_schema=False` 가 없다 ④ 최상위 의존성에서 `require_admin` 앞에는 `db` 와 응답 헤더 전용 `no_store`(결정 ii)만 온다 — 허용 목록은 함수 객체로 비교한다 — `classfit.app.deps.db` 와 `getattr(classfit.app.deps, "no_store", None)`(worker-a 의 `no_store` 커밋 전에는 None 이라 허용 목록에서 빠질 뿐 시험은 돈다). 이름 글자만 보면 다른 모듈의 `db`·`no_store` 가 인증 앞에 끼어도 통과한다(codex 계획 2차 새 2). 하한 상수는 `ADMIN_OPERATIONS_AT_LEAST = 92` 로 올린다 — 빈 목록을 돌아 통과하는 것을 막는다(codex 계획 1차 #4).
- **(vii) 운영자 미리 보기 출력의 제어·서식 문자 이스케이프.**
  - 사실: 공개 문의의 이름 칸은 C0·DEL 만(`schemas/auth.py:11` `_CONTROL`), 내용 칸은 NUL 만 막는다(`schemas/inquiry.py:68-72` `_no_nul_or_none`) — C1(U+0080–009F)·bidi(U+202A–202E·U+2066–2069)·DEL 은 `scripts/outbox_preview.py:254` 의 `json.dumps(ensure_ascii=False)` 를 지나 운영자 터미널에 날 글자로 나간다(실측). 강사 가입 이름도 같은 출력으로 간다(`_instructor_approved` :75 등).
  - 기본: `outbox_preview` 에 출력 도우미 하나 — `json.dumps(…, ensure_ascii=False)` 결과에서 유니코드 범주 Cc·Cf·Zl·Zp·Cs 글자 하나하나를 `json.dumps(ch)[1:-1]`(ensure_ascii 기본 참)로 바꾼다. BMP 글자는 `\uXXXX`, BMP 밖(예 U+E0001 — Cf)은 JSON 서로게이트 쌍 `\udb40\udc01` 이 된다(순진한 `\u` + 16진은 `\ue0001` 로 다른 글자가 된다 — codex 계획 1차 #5). 이미 `json.dumps` 가 만든 `\n`·`\u001b` 같은 이스케이프는 ASCII 라 건드리지 않는다. 짝 없는 서로게이트(Cs)는 PG text 에 저장될 수 없지만(UTF-8) 같은 규칙으로 이스케이프한다. 결과는 여전히 유효한 JSON 이고 `json.loads` 하면 원래 값이다(기존 `test_inquiry_outbox_preview_renders` 가 그대로 녹색). 모든 kind · 이미 저장된 행 · `to` 칸을 한 자리에서 덮는다. 줄을 끊는 `print` 의 줄바꿈은 출력 틀이라 대상이 아니다.
  - 대안: 입력에서 422 — `_CONTROL` 을 넓히면 그 정규식을 쓰는 모든 스키마로 번지고, 문의 내용 칸(줄바꿈·탭 허용 — T9b 결정)은 따로 검사를 둬야 하며, 이미 저장된 행은 못 막는다.
- **(viii) `inquiry_gc` 배열 바인드.**
  - 사실: `crud/inquiry.py:134·152·157` 이 id 마다 바인드를 하나씩 만든다(`IN (%(id_1_1)s, …)`). outbox 쪽이 2N 이라 N > 32,767 에서 PG 바인드 상한 65,535 에 걸린다(T9b :472).
  - 기본: 세 자리를 배열 바인드 하나씩으로 바꾼다 — 타입이 셋 다 정해져 있다(codex 계획 1차 #6): ① :134 `params["inquiry_id"].astext` 는 Text(`sqlalchemy/dialects/postgresql/json.py:174`)라 `== any_(bindparam("inquiry_ids", [str(i) …], type_=ARRAY(Text())))` — 저장된 JSON 글자를 bigint 로 캐스팅하지 않는다 ② :152 `MailOutbox.id` 와 ③ :157 `Inquiry.id` 는 `ARRAY(BigInteger())`(컴파일 실측 `= ANY (%(ids)s::BIGINT[])`, 매개변수 1). 문장 수 3 · 잠금 순서(outbox 한 문장 · id 오름차순 FOR UPDATE) · 반환값이 그대로다. 1,000건씩 나눠 지우기는 쓰지 않는다 — 묶음마다 outbox 를 잠그면 전역 오름차순이 깨져 `outbox_preview --apply` 와 교착할 수 있다.
- **(ix) `file_gc` 임시 파일 — T11 에서 뺀다(2차 입력).** 프로세스가 죽으면(SIGKILL·전원) 남는 `.tmp-*`(`service/files/store.py:60-68`)를 `gc_candidates`(:72-92)가 고르지 않는다(T1 :241). 계획 1판은 "grace 지난 `.tmp-*` 도 고르고 `remove_stale` 그대로" 였는데 codex 계획 1차 #7 이 둘을 짚었다: `remove_stale` 이 만드는 무덤 `.gc-<uuid>-.tmp-*`(:101)를 복구 길이 sha256 무덤만 알아봐(:31·:129) gc 가 죽으면 또 다른 고아가 생기고, 오래된 mtime 이 쓰는 쪽이 죽었다는 증거가 아니다(멈췄던 쓰는 쪽이 나중에 `os.replace` :65). 임시 파일 정리 정책·쓰는 쪽과의 조율을 따로 설계해야 해서 이번 범위에서 뺀다 — 결정 xvii 목록에 이 근거와 함께 옮긴다.
- **(x) 교체 뒤 옛 바이트를 gc 가 지우는지 — 시험만(T6 :388).** 교체(`…:replace`) 뒤 옛 sha256 이 참조 0 이 되어 `file_gc --apply` 가 grace 지난 옛 바이트를 지우고 새 바이트는 남기는지 단언한다.
- **(xi) 권장 구성 글자 한도 — 대조 시험. 승인자 질문 ④.**
  - 사실: 500·200 이 `schemas/diagnosis.py:49 RECO_TEXT_MAX`·`schemas/course.py:45 Line(max_length=200)` 과 `service/rules/reco.py:30·32` 두 벌이다(T9a :530). rules 는 schemas 를 import 할 수 없다(`tests/unit/test_import_rules.py:13` 의 `ALLOWED` — 계약 ① 은 service → schemas 를 막지 않는다).
  - 기본: 단위 시험 하나가 reco 상수와 schemas 쪽 값(Line 은 `typing.get_args` 의 `StringConstraints.max_length`)이 같은지 본다. 코드는 바꾸지 않는다. 대안: `core/limits.py` 에 상수를 모으고 넷이 import(공용 `Line` 정의가 바뀌어 course·pool 사용처 전부에 닿는다).
- **(xii) 0012 — 설문 양식 색인 + 공백류 CHECK. 승인자 질문 ③.**
  - 사실 ①: `survey.template_id`(FK → `survey_template.id` ON DELETE SET NULL, `models/survey.py:89-91` · `0009_surveys.py:234·255-260`)에 색인이 없다. ON DELETE 동작이 있는 FK 중 색인 없는 것은 이것 하나다. 양식 삭제·`deployed_counts`(`crud/survey_template.py:137-152`)·`lock_in_id_order(template_id=)`(`crud/survey.py:127-145`)가 설문 표를 훑는다(T8 :453).
  - 사실 ②: 1차 앞쪽 CHECK 여섯은 `length(btrim(x)) BETWEEN 1 AND n` 이라 스페이스만 지운다 — 탭·줄바꿈만 있는 값을 DB 가 받는다(T7 :424). `ck_enrollment_name`(0004:74) · `ck_instructor_name`(0005:92) · `ck_pool_course_title`·`ck_curriculum_title`·`ck_curriculum_slot_title`·`ck_advanced_course_title`(0006 `TITLE_CHECK` :29 → :106·:172·:199·:262). 0008 부터는 `~ '[^[:space:]]'` 꼴이다(`0008_session_records.py:32-33`). API 는 스키마 strip 이 먼저 막아 닿지 않는다(DB 겹 방어).
  - 기본: `alembic/versions/0012_hardening.py` 〔정함〕 — upgrade 첫 줄 `SET LOCAL lock_timeout = '5s'` · `op.create_index(op.f("ix_survey_template_id"), "survey", ["template_id"])` · CHECK 여섯을 `x ~ '[^[:space:]]' AND length(btrim(x)) <= n` 으로 drop·create(이름 그대로 · 같은 n). 다시 만들기 전에 표마다 새 식을 어기는 행을 세어 있으면 예외(행 가드 — `0005_instructor_onboarding.py:29-38` 의 `GUARD` 꼴 DO 블록 `RAISE EXCEPTION`, 쓰는 자리 :235). downgrade 는 옛 식과 색인 drop. 모델(`models/learner.py:47` · `instructor.py:34` · `pool.py:83` 의 `_TITLE_CHECK` — curriculum·advanced 가 재사용)도 같은 식으로. 대안: 색인만(CHECK 는 2차).
  - 새 식과 옛 식: 옛 식이 받던 값 중 새 식이 거절하는 것은 "스페이스가 아닌 공백류만 있는 값"(탭·줄바꿈 등)뿐이고, 새 식이 더 받는 값은 없다(같은 n 의 `length(btrim(x)) <= n` + 공백류 아닌 글자 하나 ⇒ `length(btrim(x)) >= 1`). NBSP 같은 비ASCII 공백이 `[:space:]` 인지는 DB 의 ctype 에 따른다 — 시험은 ASCII 공백류(탭 · LF · CR · VT · FF)만 단언하고 NBSP 는 dev·CI 실측값을 기록 칸에 적는다(API 는 Python `strip` 이 먼저 막는다).
  - 잠금: `ADD CONSTRAINT … CHECK` 는 ACCESS EXCLUSIVE 를 잡고 표를 훑는다. `lock_timeout` 은 잠금을 기다리는 시간만 자르고 훑는 시간은 자르지 않는다(1차 운영 전 · 행이 적어 수용 — `NOT VALID` + `VALIDATE` 는 쓰지 않는다).
  - 마이그레이션 시험(codex 계획 1차 #8 — 시험 세션 준비는 빈 DB 의 base → head 라 데이터 있는 업그레이드를 증명하지 않는다 `tests/conftest.py:56`): 새 시험이 시험 DB 에서 alembic CLI 를 자식 프로세스로(conftest 와 같은 방식) ⓐ `downgrade 0011` → 어기는 행(탭만 있는 강사 이름) 커밋 → `upgrade 0012` 가 행 가드로 실패하고 0011 그대로(트랜잭션 롤백) ⓑ 그 행을 지우고 정상 행을 둔 채 `upgrade 0012` 성공 → `downgrade 0011` → `upgrade head` 성공(정상 행이 남는다) — 정리는 무조건이고 순서가 정해져 있다(codex 계획 2차 새 1 — 어기는 행이 남은 채 `upgrade head` 를 부르면 같은 행 가드가 복구를 막고, 세션 픽스처는 다시 돌지 않는다 `tests/conftest.py:49-63`): `finally` 에서 ① 이 시험이 커밋한 행을 지운다(아는 id 로, 자기 연결 · 커밋) ② 연결을 모두 닫는다 ③ `upgrade head` 를 부르고 그 종료 0 과 `alembic current` 의 `0012 (head)` 를 단언한다. CLI 를 부를 때마다 그 전에 이 시험의 연결·트랜잭션을 모두 닫는다. 픽스처는 `migrated_db_url` 하나만 쓰고 `db_session`·`db_connection` 은 쓰지 않는다(이들은 함수 범위라 세션 내내 DDL 을 막지 않는다 `tests/conftest.py:66-82`). 모델·마이그레이션 일치: 0012 파일을 경로로 불러(`importlib`) 그 식 상수 여섯이 모델 `CheckConstraint.sqltext` 와 같은지 본다(alembic 은 CHECK 글자를 비교하지 않는다 — `alembic/autogenerate/compare/__init__.py:64-71` — CHECK 비교는 opt-in 플러그인 `checkconstraint_byname` 이고 이름만 보며 `alembic/env.py:41-42` 는 켜지 않는다). 길이 경계 n·n+1 도 본다.
- **(xiii) `ruff format` 관문. 승인자 질문 ②.**
  - 사실: 관문은 `ruff check` 뿐이다(`Makefile:45-46`). 포맷은 Claude 가 Edit/Write 한 .py 하나에만 훅이 돈다(`.claude/hooks/format-on-edit.sh:9-11`). `ruff format --check .` → 36파일(.py 35 · 루트 `2026-10-21-backend-framework-porting-guide.md` 1 — ruff 0.17.1 이 md 코드 블록도 본다). 포맷 뒤 src 줄 수는 300·500 한도 안이다(최대 `app/errors.py` 233 → 253).
  - 기본: **구현 첫 커밋**(리드)으로 `pyproject.toml` 에 `[tool.ruff.format] exclude = ["*.md"]`(참조 가이드 원문 보존) · `Makefile` lint 에 `$(BIN)/ruff format --check .` · `ruff format .` 일괄 적용(동작 변화 없음). 첫 커밋인 이유: 편집 훅이 고친 파일을 통째로 포맷해, 나중에 하면 워커 커밋에 포맷 차이가 섞인다. 포맷 전에 줄 끝 주석이 어색하게 접히는 자리(예 `app/endpoints/companies.py:114`)는 주석을 윗줄로 옮긴다. 소스 글자를 훑는 시험(`test_db_survey.py:706 test_survey_lock_call_sites` · `test_db_inquiry.py:362 _callers`)은 포맷 뒤 `make verify` 로 확인한다. CLI `--exclude` 는 쓰지 않는다(기본 제외를 덮어 `.git/dataless-backup/` 까지 잡는다). 대안: 2차.
- **(xiv) 관리자 홈 질의 다시 재기 — 기록만(T9b :475).** T9b 측정(6.663 ms)은 새 사진 셈을 모아보기 문장으로 바꾸기(`0c2b05e`) 전 값이다. 같은 도구(T9b 기록 칸 :409 의 합성 행 · `counts()` 한 문장 · `EXPLAIN (ANALYZE, BUFFERS)` 3회)로 지금 문장(3,694자 · 매개변수 30)을 다시 잰다. 합성 사진의 절반을 `uploaded_by_kind='instructor'` 로 둔다(LEFT JOIN 이 실제로 맞게). 300 ms 를 넘으면 승인자 판단 후보로 올린다.
- **(xv) T10 P4 문서.** T10 계획 기록 칸 "병합 뒤 ④" 에 병합 뒤 잰 값과 병합 커밋 CI 를 적고(T9b 가 T9a 기록 칸을 채운 꼴), plan.md T10 행 상태를 "완료. master `4c32046 merge: T10 phase1-close`" 로, spec 1절 :38 상태 칸을 병합 해시와 T11 진행으로 고친다.
- **(xvi) 실명 금지 목록 — 변경 없음. 승인자 질문 ⑤.** `scripts/forbidden_terms.txt` 는 추적 파일이고 용어 0행이다. 그 파일 :3 의 승인자 답("없음" — 실명이 생기면 r3 부록 E8 절차)이 정본이라 비어 있는 것이 정상이다. 대안: `.gitignore` 에 더할 로컬 목록 `scripts/forbidden_terms.local.txt` 를 `scripts/gate.sh` 가 함께 읽고, CI 는 secret 이 있을 때만 그 파일에 쓴다(실명은 승인자만 넣는다).
- **(xvii) 제품 결정이 필요한 후보 — T11 밖. 승인자 질문 ⑥.** 아래는 고치지 않고 plan.md 4절 "2차 입력" 에 출처와 함께 옮긴다: T4 목록 500건 상한·커서 없음 vs 홈 카드 4(T4 결정 xii · T9b :471) · 100점 환산식(T8 :449 — 승인자의 현행 식이 필요) · 예약 배포 뒤 날짜를 바꾸면 쌓인 알림 날짜가 낡음(T8 :453) · 진단 개설의 세션 제목 " (…)"(T9a :529) · `session_time` 24:xx(T7 :425 · DEC-002) · 첨부 설명 한 줄(T2b :318) · 공개홈 보유 고지 "처리 후 1년"(T9b 질문 ⑥) · spec 3절 "결정 필요" 행들 · 엔지니어링이지만 이번에 묶지 않는 것(T1 :241·:243 의 앱 시계 만료·발송 시각 · argon2 동시 상한 · auth_* 정리 잡 · 로그인 시간 차이 시험 · T3 :268 `type: ignore`(그때 세 곳 — 지금 endpoints 6곳) · T5 :356 my_courses PATCH 보기 · T2b :279 입장 조회의 `_failure(…, "ok")` 방어 갈래 · 점 세그먼트 경로의 응답 `instance`·no-store 판정 · 인증 없는 JSON 의 415 · 결정 ix 의 `file_gc` 임시 파일 정리 정책) · 운영(저장소를 iCloud 밖으로 — T5 :369 · `T8-survey` 가지의 `bfe571c` 정리 — 승인자 명령 `git branch -f T8-survey 3b4c8c4`) · SDLC 5단계(plan.md 2절 미룸 행).

**승인자 질문 (기본 / 대안)**

1. ① 본문 상한 방식 — 기본 (i) 전역 미들웨어(업로드 연산 = 업로드 상한 + 2MiB · 그 밖 1MiB, 선언 길이는 인증 전 413) / 대안 a 인증 없는 JSON 8연산만 `limited_json` / 대안 b 둘 다 / 값 대안(1MiB 대신 다른 값)
2. ② `ruff format` — 기본 넣음(구현 첫 커밋 · `make lint` 에 `--check`) / 대안 2차
3. ③ 0012 공백류 CHECK — 기본 넣음(색인과 같은 리비전) / 대안 색인만
4. ④ 권장 구성 한도 — 기본 대조 시험만 / 대안 `core/limits.py` 로 모음
5. ⑤ 실명 금지 목록 — 기본 변경 없음 / 대안 로컬 목록 + CI secret
6. ⑥ 제품 결정 후보 — 기본 T11 밖(plan.md 4절 목록) / 대안 그중 골라 T11 에(답이 필요한 것은 값을 함께 — 예: 100점 식)
7. ⑦ no-store 범위 — 기본 토큰 여섯 연산 / 대안 입장 코드 응답까지

## 바뀌는 파일

워커별 소유(같은 파일을 두 워커가 고치지 않는다 — plan.md 2절). 시험 DB 는 worker-a `classfit_test` · worker-b `classfit_b_test` · 리드·verifier `classfit_c_test`.

**리드 — 구현 첫 커밋(결정 xiii)**
- `pyproject.toml` (modify): `[tool.ruff.format] exclude = ["*.md"]`.
- `Makefile` (modify): lint 에 `$(BIN)/ruff format --check .`.
- `ruff format .` 이 고치는 .py 35개(목록은 리드 사실 조사 · 작업 순서 3 에서 다시 잰다) — 줄 끝 주석 손질 포함, 동작 변화 없음.

**worker-a — HTTP(결정 i·ii·iii·iv·v)**
- `src/classfit/app/middleware.py` (modify): `BodyLimitMiddleware` · `install_middleware` 에서 CORS 안쪽에 쌓기 · `classfit.request` 에 `TokenRedactFilter`.
- `src/classfit/app/deps.py` (modify): `IdPath`·`DayPath`(assign·records 에서 옮김) · `no_store`.
- `src/classfit/app/upload.py` (new): `MIB` · `check_length` · `invalid`.
- `src/classfit/app/endpoints/` (modify): attachments · instructor_documents · pool_files · my_attachments · photos(업로드 도우미) · courses · schedule · invite_codes · portal · enrollments · admin_instructors · tags · assign · records(경로 매개변수) · companies · auth · enter(`no_store`) · `IdPath` 를 assign 에서 들여 쓰던 나머지 여섯 diagnoses:30 · my_course_views:24 · my_courses:23 · survey_learner:31 · survey_templates:23 · surveys:28(import 만 `app.deps` 로 — verifier B3, 지금 사용처 열 곳). 줄 수는 500 한도 안.
- `tests/contracts/test_api_body_limit.py` (new): 아래 새 시험 표의 `test_body_limit_*` 일곱. CORS·요청 기록 단언이 있는 시험과 업로드 갈래는 전부 시험용 설정(업로드 상한 다섯을 모두 1MiB · `cors_origins` 하나)으로 앱을 따로 만든다(contracts conftest 의 앱·db 재정의 꼴) — 끝점 한도 2MiB · 업로드 상한 3MiB 라 큰 본문 없이 갈래를 가른다.
- `tests/contracts/test_api_no_store.py` (new): `test_no_store_token_responses`.
- `tests/contracts/test_api_path_bounds.py` (new): `test_path_id_bounds_openapi` · `test_path_id_bounds_2_63_422` · `test_path_day_bounds_422`.
- `tests/contracts/test_api_ax.py` (modify): `test_request_log_masks_token_runs` 한 시험.
- `tests/contracts/test_api_attachments.py` (modify): `test_upload_content_length_non_ascii_411` · 413 안내문 숫자 단언. 비ASCII 헤더는 값을 bytes 로 넘긴다(httpx 는 str 헤더를 ASCII 로만 인코딩해 앱 전에 실패한다 `httpx/_models.py:74` — codex 계획 1차 #10).

**worker-b — DB·스크립트·시험(결정 vi·vii·viii·x·xi·xii)**
- `alembic/versions/0012_hardening.py` (new) · `src/classfit/models/{survey,learner,instructor,pool}.py` (modify).
- `scripts/outbox_preview.py` (modify): 출력 이스케이프.
- `src/classfit/crud/inquiry.py` (modify): 배열 바인드.
- `tests/integration/test_db_hardening.py` (new): `test_survey_template_id_index` · `test_blank_check_whitespace_only_rejected` · `test_blank_check_model_matches_migration` · `test_migration_0012_guard_and_roundtrip`.
- `tests/integration/test_db_inquiry.py` (modify): `test_outbox_preview_escapes_controls`.
- `tests/integration/test_db_inquiry_gc.py` (modify): `test_inquiry_delete_beyond_bind_limit`(이름에 `gc_` 를 쓰지 않는다 — 그 파일 머리 규칙).
- `tests/integration/test_db_gc.py` (modify — 이미 `test_gc_grace` :114 · `test_gc_owner_delete_cascade` :167): `test_gc_replaced_bytes_removed`.
- `tests/unit/test_diagnosis_rules.py` (modify): `test_diagnosis_rules_reco_limits_match_schemas`.
- `tests/contracts/test_api_admin_guard.py` (modify): `test_admin_paths_instructor_403` · `test_admin_routes_require_admin_structure` · 하한 상수 `T2A_ADMIN_OPERATIONS = 25` → `ADMIN_OPERATIONS_AT_LEAST = 92`.

**리드 — 문서 커밋(결정 xv·xvii 와 각 결정의 문서 몫)**
- [`docs/process/plan.md`](../process/plan.md) (modify): 머리말 "T0a~T11 15개" · 2절 단계 표 "경화 | T11" · 3절 T10 행 상태 "완료. master `4c32046 merge: T10 phase1-close`" · T11 행 · 새 4절 "2차 입력"(결정 xvii 목록).
- [`docs/process/spec.md`](../process/spec.md) (modify): 1절 :38 상태 칸.
- [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) (modify): 4절 표에 0012 행 · :97 head 문장 · 5절 :106 "경로 규칙" 행의 공개 JSON 본문 상한 문장 · 부록 A 에 T11 행(증명 표의 시험 이름).
- [`docs/plans/T10-phase1-close.md`](T10-phase1-close.md) (modify, 기록 칸 "병합 뒤 ④" 한 행).
- `CLAUDE.md` (modify): Commands 검증 줄의 lint 설명 · Rules 에 전역 본문 상한과 `IdPath`·`DayPath` 한 줄씩.
- `docs/plans/T11-hardening.md` (이 파일) · okf 목차.

**바꾸지 않는 것:** 응답 모델·경로 집합(expected_paths 125) · `limited_json` 과 그 두 끝점 · 의존성 목록(requirements*.txt) · `scripts/gate.sh`·`scripts/forbidden_terms.txt`(결정 xvi 기본).

## 작업 순서

1. 리드: 이 계획을 okf 네 단계(`okf label --apply` → `okf link --apply` → `git diff docs` 로 새 링크 앞뒤 문장 읽기 → `okf index --apply` → `okf check --strict`) 뒤 verifier 좁은 확인과 **codex 계획 리뷰**(승인자 지시)를 거쳐 `plan: T11 hardening` 으로 커밋한다(트레일러 없음).
2. 승인자: `approve: T11` 빈 커밋. 그 전에는 코드를 바꾸지 않는다.
3. 리드: 결정 xiii 커밋 — `ruff format --check .` 를 다시 재 목록을 기록 칸에 적고, 줄 끝 주석을 손질한 뒤 `ruff format .` → `make verify`(시험 DB `classfit_c_test`) → `T11: ruff format 관문과 일괄 포맷`.
4. worker-a·worker-b 병렬(자기 소유 파일만 · 커밋은 파일 지정 · 커밋마다 `make verify` 를 자기 시험 DB 로):
   - a1 `app/upload.py` + 업로드 여섯 자리 + 비ASCII·안내문 시험 → a2 `IdPath`·`DayPath` 공용화 + 경계 시험 → a3 `BodyLimitMiddleware`(첫 단계: 읽은 바이트 413 이 pydantic 본문 길과 `request.form()` 길 둘 다 problem 으로 나오는지 실측 · 모델 이론 최대 바이트 기록) + 시험 → a4 `no_store` + 요청 기록 가림 + 시험.
   - b1 0012 + 모델 + `test_db_hardening.py`(dev `make migrate` 뒤 `alembic check` 차이 없음 · NBSP 실측) → b2 미리 보기 이스케이프 + gc 배열 바인드 + 시험 → b3 gc 교체 시험 + 한도 대조 시험 + 관리자 가드 시험.
5. 리드: 문서 커밋(바뀌는 파일 "문서 커밋" 묶음) — okf 네 단계 · `make okf` · `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` · `make gate`.
6. 검증(병렬 — CLAUDE.md "DB 쓰기·권한" 줄): 리드 증명 블록 · worker-c 대조 실험(아래 표) · 결정 xiv 측정 · 이웃 흐름(바뀐 동작 = 인증 전 413, 이웃 = 403·422) · verifier(다른 세션) · reviewer(다른 세션) · **codex 구현 리뷰**(reviewer 와 같은 때). Important 0 · codex OK 까지 고친다.
7. 리드: 계획 갱신 커밋(리뷰 · 기록 칸 · 편차) → `bash scripts/check_task_order.sh` → 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T11-hardening` → push.

## 위험

| 위험 | 알아채는 법 | 완화 |
|---|---|---|
| 1MiB 가 정상 본문을 자른다 | 기존 시험 실패 · 모델 이론 최대 바이트 기록 | 이론 최대가 넘는 모델은 승인자 질문 ① 값 대안으로 올린다. 기존 시험 558 이 그대로 녹색이어야 한다 |
| 읽은 바이트 413 이 problem 이 아닌 400·500 으로 나온다 | `test_body_limit_streamed_413` · `test_body_limit_upload_streamed_413` | 작업 순서 4 a3 첫 단계 실측. Starlette `HTTPException` 이 아니면 400(본문·Form 매개변수)·500(핸들러 안 폼·`limited_json`)이 된다 |
| multipart 라고만 붙여 JSON 연산에 큰 본문을 보낸다 | `test_body_limit_multipart_label_json_route` | 상한은 Content-Type 이 아니라 라우트로 고른다(codex 계획 1차 #1) |
| 업로드 연산 판정이 빠지거나 넘친다 | `test_body_limit_upload_routes_match_openapi` | OpenAPI 의 multipart 연산 집합과 같아야 한다 |
| 미들웨어 413 이 업로드 끝점의 자체 413 을 가린다 | `test_body_limit_upload_endpoint_own_413_first` | 업로드 상한 = 업로드 상한 최댓값 + 2MiB(끝점 한도 + 1MiB 보다 큼) — 시험용 설정에서 다섯을 같게 둬 최댓값 끝점으로 잰다 |
| 413 에 CORS 헤더가 없어 브라우저가 못 읽는다 | 두 갈래 시험의 CORS·요청 기록 단언 | CORS 안쪽 · 요청 기록 안쪽에 쌓는다 |
| 마이그레이션 시험이 시험 DB 를 0011 에 남긴다 | 다음 시험들이 0012 가 없어 실패 | `finally` 에서 행 지우기 → 연결 닫기 → `upgrade head` 와 그 성공 단언 순(결정 xii) · 그 시험만 자기 연결(바깥 트랜잭션 없음)로 행을 넣고 지운다 |
| `IdPath` 를 옮기다 경로 매개변수 하나를 빠뜨린다 | `test_path_id_bounds_openapi`(OpenAPI 의 정수 경로 매개변수 전부에 상한) | 구조 시험이 전수를 본다 |
| 0012 가 기존 행 때문에 실패하거나 downgrade 가 옛 식과 다르다 | 행 가드(`RAISE EXCEPTION`) · 시험 세션 base → head · dev `alembic check` | 대조 실험 뒤에는 같은 변이 사본으로 downgrade base(메모리 경고 — 마이그레이션 변이는 시험 DB 를 오염) |
| 일괄 포맷이 소스 글자를 훑는 시험을 깬다 | 포맷 커밋의 `make verify` | 깨지면 포맷이 아니라 시험의 글자 기준을 본다(시험을 skip 하지 않는다) |
| 이스케이프가 운영자 화면의 한글·이모지를 바꾼다 | `test_outbox_preview_escapes_controls` 의 한글 원문 단언 | 범주 Cc·Cf·Zl·Zp·Cs 만 — ZWJ 이모지는 `\u200d` 로 보이는 것을 수용(표시만) |
| 배열 바인드 시험이 느리다 | 시험 시간 | 시드는 `generate_series` 한 문장(문의 32,768 · outbox 65,536) |

## 증명

```bash
bash scripts/check_task_order.sh                                         # → "task order: OK"
make verify                                                              # → gate OK · ruff check · ruff format --check · lint-imports 3 kept · "<N> passed"(558 + 새 시험) · OKF guard OK
.venv/bin/alembic heads                                                  # → "0012 (head)"
.venv/bin/ruff format --check .                                          # → "… files already formatted"(다른 파일 0)
.venv/bin/pytest -q tests/contracts/test_api_body_limit.py tests/contracts/test_api_no_store.py tests/contracts/test_api_path_bounds.py   # → 전부 passed
.venv/bin/pytest -q tests/contracts/test_api_admin_guard.py tests/contracts/test_api_ax.py tests/contracts/test_api_attachments.py         # → 전부 passed(강사 403 92연산 포함)
.venv/bin/pytest -q tests/integration/test_db_hardening.py tests/integration/test_db_inquiry.py tests/integration/test_db_inquiry_gc.py tests/unit/test_diagnosis_rules.py   # → 전부 passed
.venv/bin/pytest -q tests/integration/test_db_gc.py                     # → 전부 passed(새 하나 포함)
.venv/bin/pytest -q tests/contracts/test_api_openapi.py                  # → passed(expected_paths 125 그대로)
git grep -c 'limited_json(' -- src/classfit/app/endpoints                # → inquiries.py:2(독스트링 :9 + 호출 :41) · survey_learner.py:1(그대로)
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh                   # → "④ 병합된 T: … · 대응표 <48+T11 행>행 중 대상 48행" · "docs check: OK"(T11 행은 병합 전이라 대상 밖)
```

**새 시험과 고정하는 것**

| 시험 | 고정하는 것 | 결정 |
|---|---|---|
| `test_body_limit_declared_413_before_auth` | 토큰 없이 관리자 JSON 연산에 `Content-Length: 1048577` → 413 problem(401 아님) · 앱이 receive 를 한 번도 부르지 않음 · `Origin` 을 붙이면 CORS 헤더 · 요청 기록에 413 | i |
| `test_body_limit_streamed_413` | 길이 선언 없는 스트림이 1MiB 를 넘으면(pydantic 본문 연산) 413 problem · CORS 헤더 · 요청 기록 413 | i |
| `test_body_limit_multipart_label_json_route` | JSON 연산에 `Content-Type: multipart/form-data` 와 선언 길이 1MiB 초과·업로드 상한 미만 → 413(JSON 상한이 걸린다) | i |
| `test_body_limit_upload_streamed_413` | 시험용 설정의 업로드 연산(관리자 첨부)에 받아들일 만한 선언 길이(1MiB)로 업로드 상한(3MiB)을 넘게 흘리면 `request.form()` 안에서 413 problem · 행·바이트 0 | i |
| `test_body_limit_upload_endpoint_own_413_first` | 같은 설정에서 선언 길이 = 끝점 한도 + 1(2MiB + 1, 업로드 상한 미만) → 끝점 자체 413 안내문(`1MiB 까지`) | i·v |
| `test_body_limit_upload_routes_match_openapi` | 미들웨어가 모은 업로드 연산 = OpenAPI requestBody 가 multipart 인 연산(8) | i |
| `test_body_limit_under_cap_unchanged` | 1MiB 이하 요청과 본문 없는 GET 은 지금과 같은 401·403·422·200 | i |
| `test_no_store_token_responses` | 여섯 연산의 200·201 에 `Cache-Control: no-store`, 회사 상세 404 에는 없음 | ii |
| `test_request_log_masks_token_runs` | `/v1/%2e/ax/<토큰>` · 같은 경로에 토큰 뒤·앞으로 글자를 붙인 꼴의 요청 기록에 날 토큰 0 | iii |
| `test_path_id_bounds_openapi` | OpenAPI 의 정수 경로 매개변수 전부에 `minimum` 과 2**63 미만 상한(`day_no` 는 60) | iv |
| `test_path_id_bounds_2_63_422` | 관리자·강사·수강생 연산 표본에 2**63 → 422 `loc ["path", …]`(500 아님) | iv |
| `test_path_day_bounds_422` | `day_no` 0·61 → 422, 1·60 은 검증을 지난다 | iv |
| `test_upload_content_length_non_ascii_411` | `Content-Length: ²`(bytes 헤더) → 411(500 아님) · 413 안내문이 설정 MiB | v |
| `test_admin_paths_instructor_403` | 관리자 92연산 전부 강사 토큰 403 `/problems/forbidden` · 연산 수 ≥ 92 | vi |
| `test_admin_routes_require_admin_structure` | 결정 vi ①~④ | vi |
| `test_outbox_preview_escapes_controls` | 출력 줄마다(줄을 끊는 줄바꿈 빼고) Cc·Cf·Zl·Zp·Cs 0자 · C1·bidi·DEL·U+2028·U+2029·U+E0001 을 넣은 행의 `json.loads` 본문이 원문(한글 포함) 그대로 · 원래 있던 `\n` 이스케이프 그대로 | vii |
| `test_inquiry_delete_beyond_bind_limit` | 문의 32,768건 · outbox 65,536행을 `--older-than-days 365 --apply` 가 종료 0 으로 다 지움 · cutoff 안쪽 문의와 다른 kind outbox 는 남음 · 세 DELETE·SELECT 문장의 id 배열 바인드가 문장마다 하나(컴파일 단언 — astext SELECT 는 JSON 키 매개변수가 하나 더) | viii |
| `test_gc_replaced_bytes_removed` | 교체 뒤 옛 바이트는 gc 가 지우고 새 바이트는 남음 | x |
| `test_diagnosis_rules_reco_limits_match_schemas` | reco 500·200 = schemas 500·200 | xi |
| `test_survey_template_id_index` | `pg_indexes` 에 `ix_survey_template_id` | xii |
| `test_blank_check_whitespace_only_rejected` | 여섯 표에 ASCII 공백류(탭·LF·CR·VT·FF)만 있는 값 INSERT → CHECK 위반 · 길이 n 은 들어가고 n+1 은 위반 | xii |
| `test_blank_check_model_matches_migration` | 0012 의 식 상수 여섯 = 모델 `CheckConstraint.sqltext` | xii |
| `test_migration_0012_guard_and_roundtrip` | 결정 xii 마이그레이션 시험 ⓐ 행 가드 실패(안내문) + 0011 그대로 ⓑ 정상 행으로 upgrade → downgrade → upgrade head | xii |

**대조 실험**(커밋 뒤 임시 사본에서 변이 하나씩 — CLAUDE.md "대조 실험은 커밋 뒤나 임시 사본에서만"). 기대는 전부 빨강.

| # | 변이 | 빨개질 시험 |
|---|---|---|
| 1 | `BodyLimitMiddleware` 를 쌓지 않음 | `…_declared_413_before_auth` · `…_streamed_413` |
| 2 | 읽은 바이트 갈래 제거(선언 길이만) | `…_streamed_413` · `…_upload_streamed_413` |
| 3 | 상한을 Content-Type 으로 고름(1판 설계) | `…_multipart_label_json_route` |
| 4 | 업로드 상한 = 업로드 상한 최댓값(+2MiB 없이) | `…_upload_endpoint_own_413_first` |
| 5 | 업로드 연산 판정을 비움(모두 1MiB) | `…_upload_routes_match_openapi` · `…_upload_endpoint_own_413_first` |
| 6 | 미들웨어를 CORS 바깥에 쌓음 | `…_declared_413_before_auth`(CORS 단언) |
| 7 | 회사 상세 GET 의 `no_store` 제거 | `test_no_store_token_responses` |
| 8 | 요청 기록의 `mask_runs` 와 필터 제거 | `test_request_log_masks_token_runs` |
| 9 | 요청 기록 가림을 정확히 32자(`TOKEN_RE`)로만 | `test_request_log_masks_token_runs`(뒤에 글자 붙인 꼴) |
| 10 | courses 모듈만 `IdPath` 를 `int` 로 되돌림 | `test_path_id_bounds_openapi` · `…_2_63_422` |
| 11 | `DayPath` 상한 61 | `test_path_day_bounds_422` |
| 12 | `check_length` 의 ASCII 검사 제거 | `test_upload_content_length_non_ascii_411` |
| 13 | 관리자 연산 하나를 `CurrentPrincipal` 로 | `test_admin_paths_instructor_403` · `…_structure` |
| 14 | 미리 보기 이스케이프 제거 | `test_outbox_preview_escapes_controls` |
| 15 | BMP 밖 글자를 `\u` + 16진으로 | `test_outbox_preview_escapes_controls`(U+E0001 왕복) |
| 16 | gc 를 `in_` 으로 되돌림 | `test_inquiry_delete_beyond_bind_limit` |
| 17 | 0012 에서 색인 빼기 | `test_survey_template_id_index` |
| 18 | 0012 에서 CHECK 하나를 옛 식으로 | `test_blank_check_whitespace_only_rejected` · `…_model_matches_migration` |
| 19 | 0012 의 행 가드 제거 | `test_migration_0012_guard_and_roundtrip`(안내문 단언) |
| 20 | `reco.RECO_TEXT_MAX = 501` | `test_diagnosis_rules_reco_limits_match_schemas` |
| 21 | 한 줄을 포맷 밖으로 | `make lint` 실패 |

## 리뷰

(다른 세션의 reviewer 가 쓴다. Important n건 · Nit n건, 소견과 고친 커밋. Important 0 이 될 때까지 고친다 — r3 §5.1-3)

## 계획과 다르게 한 것

(구현 중 채운다. 비어 있으면 계획대로다.)

| 기록 칸 | 값 |
|---|---|
| 승인(approve 커밋 해시) | |
| codex 계획 리뷰 판정 | 1차(1판) **BLOCK** 차단 1 · 중대 8 · 경미 2 → 2차(3판) **BLOCK** 1차 11건 중 9 CLOSED · 새 중대 1 · 경미 1 → 3차(4판) **OK** — 남은 넷 CLOSED · 새 결함 없음. 사이에 verifier 좁은 확인(2판) FAIL 차단 3 · 권고 7 · nit 12(수치·인용 전부 MATCH) → 3판 반영 |
| `ruff format --check .` 목록(작업 순서 3) | |
| 모델 이론 최대 바이트 · 읽은 바이트 413 실측(작업 순서 4 a3) | |
| `make verify` 끝 20줄(최종) | |
| 증명 블록 출력 | |
| 대조 실험 21개 | |
| 0012 NBSP 실측(dev · CI) | |
| 이웃 흐름(인증 전 413 · 403 · 422) | |
| 홈 질의 `EXPLAIN (ANALYZE, BUFFERS)`(결정 xiv) | |
| verifier · reviewer · codex 구현 리뷰 | |




---

# Resources

- 1차 태스크 계획들의 "리뷰"·"계획과 다르게 한 것" 절(저장소 `docs/plans/`) · T10 계획 P4.
- 리드 사실 조사 셋(2026-10-24, 읽기 전용, 세션 스크래치 — 저장소 밖): HTTP(본문 연산 64 · 토큰 응답 · 경로 가림 실측) · 스크립트·도구(이스케이프 · 바인드 · ruff · 한도 · 색인 · 측정) · 권한·누적(관리자 92연산 · 열린 항목 31건).
