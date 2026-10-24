"""만족도 설문 구성요소(T8 결정 xx): 양식(templates) · 배포(deploy) · 닫기·다시 열기·고치기(close) · 응답(respond) ·
결과(results) · 읽기 모양(views) · 강의 판정(scope).

잠금 순서는 template → course → survey → survey_response 의 한 방향이다(결정 xix). crud 는 모듈 별칭(crud_*)의
속성으로 부른다 — 행동 시험의 감싸개·정적 시험이 그 꼴을 본다. 다른 service 구성요소(courses·enroll·files 등)는
import 하지 않는다 — 강의·등록은 crud 로 읽는다. 상태·집계 규칙은 classfit.service.rules.survey · survey_stats 에서 가져온다.
정면 재노출은 두지 않는다. 부르는 쪽은 하위 모듈(classfit.service.surveys.deploy 등)에서 가져온다.
"""
