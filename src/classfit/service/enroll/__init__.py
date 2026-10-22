"""입장 구성요소: 초대코드 조회와 입장·재입장(enter). ADR-002 · 기획안 P3 · T2b 계획 결정 i~v.

판정만 하고 결과 값을 돌려준다. 세션 발급(service.auth)은 끝점이 잇는다(계약 ② 로 구성요소끼리 모른다).
enrollment 행은 enter.enter_course() 에서만 만든다. 정면 재노출은 두지 않는다.
"""
