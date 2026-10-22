"""규칙 구성요소: 강의·코드 상태(status) · 일정(schedule) · 초대코드 모양(invite).

service 의 최하위 순수 함수다(Design 5절 14). DB·crud·models 를 import 하지 않고, 오늘은 인자로 받는다(5절 15).
정면 재노출은 두지 않는다. 부르는 쪽은 하위 모듈(classfit.service.rules.status 등)에서 가져온다.
"""
