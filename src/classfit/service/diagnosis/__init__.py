"""진단·회사·링크 구성요소(T9a): 회사(companies) · 회차(rounds) · 링크 발급·회수(links) · 공개 응답(public) ·
리포트·권장 구성 후보(reports).

쓰기는 전부 회사 행 FOR UPDATE(crud.company.lock_company) 아래다(결정 xi). 공개 응답은 토큰이 주체다(Design :59).
crud 는 모듈 별칭(crud_*)의 속성으로 부른다 — 행동 시험의 감싸개·정적 시험이 그 꼴을 본다. 다른 service 구성요소
(courses 등)는 import 하지 않는다 — 강의·풀 과정은 crud 로 읽는다. 문항·산식·권장 구성 초안은 classfit.service.rules.
diagnosis · reco 에서 가져온다. 정면 재노출은 두지 않는다.
"""
