"""강사 구성요소: 가입과 인증 코드 요청(signup) · 프로필과 재신청(profile) · 관리자 상태 전이(status). T3.

단일 진입점(Design 5절 13): 강사 행은 signup.signup() 에서만 만든다. 인증 코드를 만드는 곳은 이 구성요소가 아니다
(요청은 outbox 에 요청 행 id 만 쌓고, 코드는 발송 쪽 scripts.outbox_preview 가 auth 구성요소로 만든다).
로그인·세션은 auth, 서류 바이트는 files 구성요소다. 다른 service 구성요소를 import 하지 않는다(계약 ②).
끝점의 pydantic 모델을 받지 않고 키워드 인자·dict 를 받는다. 정면 재노출은 두지 않는다.
"""
