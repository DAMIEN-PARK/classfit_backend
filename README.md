# classfit (임시 이름) — BCTONE 강사관리 플랫폼 백엔드

(주)비씨티원 AX 교육 운영 플랫폼의 백엔드. 기획은 `기획/`, 화면 시안은 `시안/`에 있다.
코드 뼈대는 `2026-10-21-backend-framework-porting-guide.md`(BHQ 방식)를 따른다.

## 스택

Python 3.14 · FastAPI · SQLAlchemy 2.0 async · psycopg 3 · Alembic · pydantic-settings · PostgreSQL 17

## 처음 한 번

```bash
make venv          # venv 는 .venv.nosync(iCloud 동기화 제외), .venv 는 그 링크. pip-tools 포함
make lock          # requirements.in → requirements.txt (의존성을 바꿨을 때만)
make install       # 설치 + 편집 설치
make db-create     # 로컬 Postgres 17 에 classfit_dev · classfit_test 생성
cp .env.example .env
make migrate       # alembic upgrade head
make hooks         # .githooks/pre-push 연결
```

## 매일

```bash
make run           # uvicorn classfit.main:app --reload  (http://127.0.0.1:8000/v1/health)
make verify        # editable-check → gate → lint → lint-imports → test
```

시험은 라이브 Postgres 로 돈다. `CLASSFIT_TEST_DATABASE_URL` 이 없으면 건너뛰지 않고 실패한다.

## 설정 우선순위

셸 환경 변수 > `.env` > 코드 기본값. 앱(pydantic-settings)·`make test|run|migrate`(dotenv `--no-override`)·pytest 직접 실행(시험 DB URL 만 `.env` 보충) 모두 같은 순서다.
`.env` 는 커밋하지 않는다(`.gitignore` 의 `.env`, `.env.*`). 값에 `$`·`#`·따옴표가 있어도 그대로 읽힌다.

## 폴더

```
src/classfit/
  core/       설정 · 공용 도우미          (아무 층도 모른다)
  database/   엔진 · 세션 팩토리
  models/     SQLAlchemy 표 (__init__ 이 전부 재노출)
  schemas/    pydantic 입출력 모양
  crud/       DB 읽기·쓰기 (첫 인자 session, flush 까지만)
  service/    규칙과 흐름 (구성요소마다 폴더)
  app/        HTTP: routers · deps · errors · middleware · endpoints/
  main.py     create_app() + lifespan
alembic/      마이그레이션 (리비전 id 는 손으로 0001, 0002 …)
tests/        unit(DB 없음) · integration · contracts (라이브 PG)
scripts/      gate.sh · check_file_size.py
```

import 방향(위층 → 아래층)은 `pyproject.toml` 의 import-linter 계약이 지킨다. 요청 1개 = 트랜잭션 1개이고, service·crud 는 `flush` 까지만 한다.
