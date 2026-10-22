"""파일 저장 포트(ADR-003). 1차는 로컬 디스크 `FILE_STORE_ROOT`, 바이트는 sha256 내용 주소.

세션 첨부 넣기·지우기는 `attachments`(T2b)가 store 를 쓴다.
정면 재노출은 두지 않는다. 부르는 쪽은 하위 모듈(`classfit.service.files.store` 등)에서 가져온다.
"""
