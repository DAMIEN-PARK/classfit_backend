<!-- okf:generated — scripts/okf/okf.py index 가 만든다. 손으로 고치지 않는다. -->

# Readme

* [README.md](README.md)

# Task Plan

* [Plan: T0a sdlc-bootstrap](T0a-sdlc-bootstrap.md) - SDLC 1~3단계(계획·차단기·자동 문지기)와 ADR-002·003 을 ClassFit 저장소에 까는 첫 태스크 계획
* [Plan: T0b sdlc-okf](T0b-sdlc-okf.md) - SDLC 4단계 문서 사슬(intent·spec·Design·ADR-001·004·plan·agent·research)과 OKF 1~7단계(okf.py·okf.toml·label·link·index·check·guard)를 깔고, T0a 리뷰 잔여 nit 와 CI 액션 판을 정리하는 태스크 계획
* [Plan: T1 common-base](T1-common-base.md) - 관리자 로그인·auth_session·auth_attempt·outbox·issue_email_code()·stored_file·파일 Bearer 전달·flush_or_conflict·Today·커서·관리 명령 3·import-linter 계약 ② 와 마이그레이션 0002 를 까는 공통 바닥 태스크 계획
* [Plan: T10 phase1-close](T10-phase1-close.md) - T9b 병합·push 뒤 1차 마감 기록만 남기는 문서 전용 태스크 계획 — spec 1절 plan.md 행 "1차 완료" · check_docs ④ 대상 행 수 · E-15(T9b 병합 커밋 CI) 결론을 T9b 계획 기록 칸과 plan.md 에 적는다. 코드·마이그레이션 없음
* [Plan: T11 hardening](T11-hardening.md) - 1차가 남긴 엔지니어링 후보를 묶은 경화 태스크 계획 — 전역 본문 상한(인증 전 413), 토큰이 실리는 응답의 no-store, 요청 로그 토큰 가림, 정수 경로 매개변수 상한, 업로드 길이 검사 공용화, 관리자 92연산 강사 403 시험, 운영자 미리 보기 제어 문자 이스케이프, inquiry_gc 배열 바인드, 0012(설문 양식 색인 · 공백류 CHECK), ruff format 관문, T10 P4 문서와 2차 입력 목록
* [Plan: T2a open-course](T2a-open-course.md) - 빈 강의 개설 + 초대코드 발급(한 트랜잭션)·일정·섹션·세션·코드 관리·course_status_at·code_state_at(+SQL 판)·golden 추출·깨진 커서 422 와 마이그레이션 0003 을 까는 태스크 계획
* [Plan: T2b enter-portal](T2b-enter-portal.md) - 수강생 입장·재입장(초대코드 + 이메일)·learner(이메일만)·enrollment(이름·부서)·포털·관리자 첨부(pdf·link)·파일 열람 href·정원·재발급 잠금과 마이그레이션 0004 를 까는 태스크 계획
* [Plan: T3 instructor-onboarding](T3-instructor-onboarding.md) - 강사 가입(이메일 인증 코드 해시·분야 태그·약관 판본)·로그인·프로필·서류 3종(열람 audit)·관리자 승인/반려/정지/해제(A2 상태 4행 전이)·태그 설정과 마이그레이션 0005 를 까는 태스크 계획
* [Plan: T4 course-pool](T4-course-pool.md) - 과정 풀(AX 과정·강사 고유 과정·강사 역량·커리큘럼·심화 과정)과 마이그레이션 0006, 멱등 관리 명령 import_ax_catalog, 공개 카탈로그 질의 함수 published_catalog() 를 까는 태스크 계획
* [Plan: T5 course-assign](T5-course-assign.md) - 강의 개설 완성(지난 강의 복제·강사 커리큘럼 시작점)·과정 풀에서 세션 고르기·강사 배정(승인 강사만)·기본 강의안 행 복제(같은 sha 다른 key)·강사의 배정 강의 열람과 내 세션 수정, 마이그레이션 0007 을 까는 태스크 계획
* [Plan: T6 instructor-attachments](T6-instructor-attachments.md) - 강사가 배정된 자기 세션에 첨부(pdf·오피스·HTML 패키지 zip·이미지 파일과 링크)를 넣고·고치고·바꾸고·지우게 하고, HTML 패키지 열기 501·교체 뒤 옛 href 404·gc 유예·소유자 삭제와 파일 행 같은 트랜잭션을 고정하며, 강사 화면 읽기(홈·포털 미리 보기·초대코드·안내문·명단 — 명단은 최소 노출)를 더하는 태스크 계획(마이그레이션 없음)
* [Plan: T7 session-records](T7-session-records.md) - 0008 로 세션마다 교육 기록 하나(session_record)와 교육 사진(photo)을 두고, 강사·관리자의 기록 저장·확인·계획대로 기록·일괄 확인의 상태 전이표(none → done → ok, 확인 뒤 강사 수정 → done)를 행마다 시험으로 고정하며, 사진 올리기·설명·지우기(예정 차시 409 · 남의 사진 403 · 공개 표시 없음)와 관리자 열람(강의 기록 · 모아보기 · 내려받기 목록 · 확인 표시)을 더하고, 포털에 기록·사진 칸이 없음을 재는 태스크 계획
* [Plan: T8 survey](T8-survey.md) - 0009 로 설문 양식(survey_template · 기본 양식 시드)·배포 설문(survey · 강의당 현재 설문 1개 · 문항 스냅샷 · 날짜 단위 열림·닫힘)·응답(survey_response · 1인 1회)을 두고, 관리자 양식 CRUD·여러 강의 배포·마감·다시 열기·문항 잠금(응답 1건 뒤 409)·A5 집계와 수강생 조회·1회 제출(두 번째 409 · 열린 설문만 · 필수 누락 422)·강사 I7 결과(배정 강의만 · 마감 뒤 · 최소 응답 수 임계)를 더하며, I7·A5 결과·포털 배너·명단 응답 여부 칸 어디에도 개인 키·제출 시각이 없음을 재고, 열린 설문 배포 동시성 1개를 E-11 에 더하는(4 → 5) 태스크 계획
* [Plan: T9a diagnosis](T9a-diagnosis.md) - 0010 으로 회사(company)·진단 회차(diagnosis, 회사당 회차 번호 유일 · 사전/사후 · 방문/링크 · draft/review/final · 17지표 답 JSON)·진단 링크(diag_link, 토큰 유일 · 회사당 open 1)를 두고 course 에 company_id 를 더하며, 관리자의 회사·회차·링크 관리와 공개 토큰 응답(세션 없음 · 만료/회수/제출은 410 이유 코드 · 제출 응답에 점수 없음 · 제출 즉시 닫힘 + review 회차 생성)·시안 calc 와 같은 산식(golden)·확정 진단의 권장 구성으로 강의를 만드는 개설 시작점 ③(확정 전 409)을 더하는 태스크 계획
* [Plan: T9b inquiry-home](T9b-inquiry-home.md) - 0011 로 교육 문의 표(inquiry, Company 연결 없음)를 두고 공개 접수 끝점(필수 넷·형식·동의 422 · 본문 상한 413 · honeypot 은 정상과 같은 200 영수증이되 0행 · 같은 이메일+내용 1분 안 재제출은 같은 영수증 · 이메일당 하루 상한 429 · 수신 주소 미설정 501 · outbox 두 행의 params 에 내용 없음)과 관리자 홈(승인 대기 · 진행 강의 · 미배정 세션 · 미검토 등록 · 열린 설문 · 진단 검토 대기 · 미기록 · 새 사진 · 최근 이력 — 셈마다 상세 목록과 같은 조건, 홈 service 호출당 문장 둘)과 진단 회차 목록(관리자 · status 필수 · 홈의 진단 검토 대기 셈과 같은 문장)과 문의 삭제 관리 명령(접수 시각 + 365일 보유)을 더하고, 1차 마지막 병합이라 r3 §6 최종 개수 기준과 마감 가지를 증명에 넣는 태스크 계획
