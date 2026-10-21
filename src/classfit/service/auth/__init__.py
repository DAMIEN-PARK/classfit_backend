"""인증 구성요소: 관리자 로그인(login) · 세션 토큰(sessions) · 인증 코드(email_code).

정면 재노출은 두지 않는다. 부르는 쪽은 하위 모듈(classfit.service.auth.login 등)에서 가져온다.
다른 service 구성요소를 import 하지 않는다(import-linter 계약 ②). 구성요소 사이의 읽기는 crud 를 거친다.
"""
