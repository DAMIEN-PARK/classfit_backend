"""교육 문의 구성요소(T9b 결정 xii): 공개 폼 접수(receive).

문의 행은 receive.receive_inquiry() 만 만든다(단일 진입, 결정 xi). 다른 service 구성요소는 import 하지 않고 crud 로만
읽고 쓴다. crud·rules 는 모듈 별칭(crud_*·rules_*)의 속성으로 부른다 — 시험이 영수증 난수를 monkeypatch 한다.
정면 재노출은 두지 않는다.
"""
