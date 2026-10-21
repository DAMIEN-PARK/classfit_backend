<!-- okf:generated — scripts/okf/okf.py index 가 만든다. 손으로 고치지 않는다. -->

# ADR

* [ADR-001: 시안 HTML 은 참고 자료로만 쓴다](ADR-001-mockups.md) - 관리자·강사·학습자 시안 HTML 을 서빙하거나 치환하지 않고 화면 참고와 golden 기대값 출처로만 쓰며, 1차 산출물은 API·OpenAPI·계약 시험으로 하는 결정
* [ADR-002: 수강생 세션은 강의 하나에 묶는다](ADR-002-learner-session.md) - 비밀번호 없는 수강생의 토큰을 강의 범위로 묶고, 이름·부서는 강의마다 enrollment 에 두며, 세션 수명은 1일로 하는 결정
* [ADR-003: 파일·메일·문서 열기는 포트 뒤에 둔다](ADR-003-external-ports.md) - 파일은 Bearer + 범위 판정 뒤 바이트와 불투명 href 로, 메일은 outbox 로, PDF·HTML 패키지 열기는 501 로 두는 1차 외부 포트 결정
* [ADR-004: 공개홈은 화면을 보류하고 API 만 만든다](ADR-004-public-home.md) - 루트로 옮겨진 공개홈을 별도 트랙으로 보고, 화면은 보류하되 입장·강사 가입·자가진단·교육 문의 API 는 만들고 카탈로그는 질의 함수까지만 두는 결정
