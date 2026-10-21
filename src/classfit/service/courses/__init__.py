"""강의 구성요소: 개설(open) · 초대코드(codes) · 일차와 일정표(days) · 섹션·세션(sections).

단일 진입점(Design 5절 13): 강의 개설 + 코드 발급은 open.open_course(), 초대코드는 codes.issue_invite_code() 로만 만든다.
정면 재노출은 두지 않는다. 부르는 쪽은 하위 모듈(classfit.service.courses.open 등)에서 가져온다.
규칙(상태·일정·코드 모양)은 classfit.service.rules 에서 가져온다. 다른 service 구성요소(auth·files)는 import 하지 않는다.
"""
