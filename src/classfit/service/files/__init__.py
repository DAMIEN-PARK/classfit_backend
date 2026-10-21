"""파일 저장 포트(ADR-003). 1차는 로컬 디스크 `FILE_STORE_ROOT`, 바이트는 sha256 내용 주소.

정면 재노출은 두지 않는다. 부르는 쪽은 `classfit.service.files.store` 에서 가져온다.
"""
