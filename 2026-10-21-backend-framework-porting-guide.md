---
type: Howto
title: 백엔드 프레임워크 이식 안내서 (BHQ 방식, 도커 제외)
description: BHQ 백엔드의 스택(FastAPI · SQLAlchemy async · psycopg3 · Alembic · pydantic-settings), 종류 우선 폴더 배치, 층별 핵심 규칙, make verify 품질 관문, 옮기는 순서와 함정을 한눈에 정리한 개요. Docker·배포는 뺐다
date: 2026-10-21
tags: [backend, fastapi, sqlalchemy, alembic, python, architecture, template, bhq, porting]
Archives: false
URL: ""
---

# 백엔드 프레임워크 이식 안내서 (BHQ 방식, 도커 제외)

> **이 문서 쓰는 법**
> - 개요다. 깊은 설명 대신 "무엇을 어디에, 왜" 만 적었다. 자세한 것은 BHQ 원본 파일(Resources)을 연다.
> - **Claude Code 에게:** "이 문서 §5 순서대로 새 저장소에 뼈대를 깔아 줘. 패키지 이름은 `<pkg>` 로" 라고 말한다.
> - 기준: BHQ backend `origin/main` `2e79c0e` (2026-10-21). 코드 조각은 BHQ 원문에서 자르고 줄인 **발췌**다. 따로 떼어 돌려 보지는 않았다.
> - **짝 문서:** 개발 절차는 [`2026-10-06-ai-native-sdlc-porting-guide.md`](2026-10-06-ai-native-sdlc-porting-guide.md), 문서 정리는 [`2026-10-21-okf-sdlc-porting-guide.md`](2026-10-21-okf-sdlc-porting-guide.md). 이 문서는 **코드의 뼈대**만 다룬다.

---

## 0. 30초 요약

**비유: 아파트.** 층마다 하는 일이 정해져 있다. 엘리베이터는 **아래로만** 다닌다. 위층(HTTP)은 아래층(DB)을 부를 수 있지만, 아래층은 위층을 모른다. 이 규칙을 사람이 아니라 기계(import-linter)가 지킨다.

```
app · mcp · cli        ← 문 (HTTP·도구·명령줄)
      ↓
service                ← 규칙과 흐름
      ↓
crud                   ← DB 읽기·쓰기
      ↓
schemas                ← 입출력 모양 (pydantic)
      ↓
models · database      ← 표 정의 · 연결
      ↓
core                   ← 설정 · 보안 · 커서 같은 공용 도우미
```

**다섯 원칙**
1. **종류 우선 폴더.** 바깥은 종류(models·crud·service…), 안쪽은 도메인 파일.
2. **트랜잭션 주인은 하나.** API 는 요청 1개 = 트랜잭션 1개. service·crud 는 `flush` 까지만 한다.
3. **미구성은 실패다.** 설정이 없으면 조용히 기본값으로 넘어가지 않고 이름을 대며 멈춘다.
4. **경계는 기계가 지킨다.** import 방향(import-linter) · 파일 크기 · 금지 의존성 · 비밀 · 주소를 `make verify` 가 막는다.
5. **시험은 진짜 DB 로.** 통합·계약 시험은 라이브 Postgres 에서 돈다. DB 주소가 없으면 건너뛰지 않고 실패한다.

---

## 1. 스택

판은 2026-10-21 `requirements.txt` · `requirements-dev.txt` 의 고정 값이다.

| 역할 | 쓰는 것 | 판 |
|---|---|---|
| 언어 | Python (pyenv `.python-version`) | 3.14.7 |
| 웹 | FastAPI / Starlette / uvicorn | 0.141.1 / 1.6.0 / 0.52.4 |
| ORM | SQLAlchemy **async** | 2.0.52 |
| DB 드라이버 | psycopg 3 (`postgresql+psycopg://`) | 3.3.5 |
| 마이그레이션 | Alembic | 1.19.2 |
| 벡터 | pgvector (Postgres 확장 + 파이썬 패키지) | 0.5.0 |
| 모양·설정 | pydantic / pydantic-settings | 2.13.5 / 2.15.0 |
| 바깥 호출 | httpx | 0.28.1 |
| 에이전트 그래프 | langgraph (LangChain 은 금지) | 1.2.11 |
| MCP 서버 | mcp | 2.2.0 |
| 개발 도구 | ruff · pytest · pytest-asyncio · import-linter · pip-tools | 0.16.6 · 9.1.1 · 1.4.0 · 2.14 · 7.6.1 |

**쓰지 않는 것:** asyncpg(드라이버는 psycopg 하나) · 동기 세션 · LangChain(`langgraph` 의 이행 의존성 `langchain-core` 만 허용) · OpenAI SDK(OpenAI 호환 API 는 httpx 로 직접 부른다).

**의존성 관리 (pip-tools)**
- `requirements.in` 에 직접 의존성만 적는다. `make lock` 이 `requirements.txt` 를 만든다.
- `requirements-dev.in` 첫 줄 `-c requirements.txt` 로 개발 도구 판을 런타임 판에 묶는다.
- `pyproject.toml` 은 의존성을 `dynamic` 으로 두고 `requirements.in` 을 읽는다. 그래서 `.in` 의 주석은 줄 단독으로만 쓴다.
- `src/` 배치 + **편집 설치**(`pip install --no-deps -e .`). uvicorn·import-linter 가 패키지를 찾으려면 꼭 필요하다.

---

## 2. 폴더 배치 (종류 우선)

```
<repo>/
├── src/<pkg>/
│   ├── core/          설정(config.py) · API 키 해시 · Fernet · 커서 · 공용 HTTP 클라이언트
│   ├── database/      엔진 · 세션 팩토리
│   ├── models/        SQLAlchemy 표. __init__.py 가 전부 재노출(alembic 이 한 줄로 다 보게)
│   ├── schemas/       pydantic 입출력 모양. JSONB 모양 검사는 schemas/json/*.json
│   ├── crud/          DB 읽기·쓰기 함수. 첫 인자가 session
│   ├── service/<구성요소>/   규칙과 흐름. 구성요소마다 폴더
│   ├── app/           routers.py(등록부) · deps.py(세션·인증) · errors.py · middleware.py · endpoints/<자원>.py
│   ├── mcp/ · cli/    HTTP(/v1)만 부르는 얇은 손님
│   ├── main.py        API 진입점 (uvicorn <pkg>.main:app)
│   └── worker.py      백그라운드 워커 진입점 (python -m <pkg>.worker)
├── alembic/  alembic.ini
├── tests/{unit, integration, contracts, fixtures}   conftest.py · stale_patch_guard.py
├── scripts/           gate.sh · check_file_size.py · check_secrets.sh · 관리 명령(python -m scripts.x)
├── pyproject.toml  requirements.in  requirements-dev.in  Makefile
└── .githooks/pre-push  .github/workflows/ci.yml
```

**배치 규칙**
- **import 방향 계약 셋**(pyproject 의 import-linter). ① 종류 계층(§0 그림) ② `service` 안 구성요소끼리의 위아래 ③ 코어 집합(models·schemas·crud·database·core)은 소비자(app·mcp·cli·`main`·`worker`)를 import 하지 않는다. BHQ 는 여기에 계정·메신저 경계 계약을 더해 7건이다.
- **새 구성요소를 만들면 ②·③ 목록에 같이 더한다.** 안 더하면 아무 계약에도 안 걸린다(BHQ 실측: 한 구성요소가 그렇게 병합됐다).
- **파일 크기 상한**(`check_file_size.py`). `src/<pkg>/**` 만 본다. models·schemas 는 면제, `app/endpoints/` 500줄, 나머지 300줄. 넘기려면 앞 30줄 안에 `# oversize: <상한> <사유 10자 이상>` 한 줄을 적는다. 숫자는 알람이고, 쪼갤 자리는 "고치는 이유가 둘인가"로 정한다.
- **재노출 `__init__.py` 는 정면(facade)일 때만.** 예: `models`, `service/llm`(게이트웨이), `service/pages`(단일 진입점). 줄 수 때문에 쪼갠 흔적으로 만들면 이름이 사는 자리가 둘이 되어 시험의 `monkeypatch` 가 껍데기만 때린다(§3.5).

---

## 3. 층별 핵심 규칙

### 3.1 진입점·HTTP

- **앱 팩토리 + lifespan.** `create_app()` 이 앱을 만들고, `lifespan` 이 엔진을 만들어 `app.state.session_factory` 에 둔 뒤 끝날 때 `dispose` 한다. 엔진은 **기동 때** 실패해야 한다(첫 요청에서 실패하면 healthcheck 가 이미 통과한 뒤다).
- **미들웨어 순서:** 오류 처리기 → 요청 기록 → GZip → CORS(설정한 출처가 있을 때만) → 라우터.
- **문서 주소:** `/v1/openapi.json` 은 늘 연다(계약 정본). Swagger(`/v1/docs`)는 개발 스위치를 켤 때만 연다.
- **라우터 등록부** `app/routers.py` 의 튜플 하나. 새 자원은 여기만 고친다. 라우터마다 `APIRouter(prefix="/v1")`.
- **인증:** `Authorization: Bearer <키>` → `Caller`(주체·회사·principals·권한). 권한은 타입 별칭으로 건다: `ReadCaller` · `WriteCaller` · `ApproveCaller`.
- **오류 본문은 하나:** `application/problem+json` 의 `{type, title, status, detail, instance, …}`. 처리기 다섯(우리 오류 · 도메인 오류 · Starlette HTTP · **마지막 그물 500** · 요청 검증 422). 401 에는 `WWW-Authenticate: Bearer`.
- **상태 코드:** 403 = 자격 없음(남의 회사 자원도 404 대신 403) · 409 = 상태 충돌 · 410 = 파기됨 · 422 = `violations[{loc,msg,type}]` · 501 = 미구성 · 503 = 지금 확인 불가(401 로 뭉개지 않는다).
- **목록 응답:** 커서 페이지 `{items, next_cursor, has_more}`. 커서는 `base64url({"t":시각,"i":id})`. 동작은 `POST /v1/<자원>/{id}:reject` 처럼 접미사로.

**발췌 — 세션·권한 의존성** (`src/bhq/app/deps.py`, 줄임)

```python
async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """요청 1개 = 트랜잭션 1개."""
    factory = request.app.state.session_factory
    async with factory() as session, session.begin():
        yield session

DbSession = Annotated[AsyncSession, Depends(db)]

def require(perm: str):
    async def dependency(who: CurrentCaller) -> Caller:
        if not who.can(perm):
            raise forbidden(f"이 요청에는 org 범위 '{perm}' 자격이 필요합니다")
        return who
    return dependency

ReadCaller = Annotated[Caller, Depends(require("read"))]
WriteCaller = Annotated[Caller, Depends(require("write"))]
```

### 3.2 데이터

- **엔진:** URL 이 `postgresql+psycopg://` 로 시작하지 않으면 거부. `pool_pre_ping=True`, 세션은 `expire_on_commit=False`.
- **트랜잭션 주인:** API 는 `db()` 의존성, 워커는 레인 루프, 관리 명령은 `main_async` 한 곳. service·crud 는 `flush` 까지만 한다.
- **모델:** `Base` 에 `naming_convention`(제약 이름 고정) + `datetime → timestamptz`. id 는 `BigInteger Identity(always=True)`. 상태 열은 PG ENUM 대신 `Text + CheckConstraint`. JSON 은 전부 `JSONB`. 공통 열은 믹스인(`TimestampMixin`, 큐 표의 `JobStateMixin`).
- **목록 쿼리의 첫 WHERE = 회사 + 읽기 권한.** `org_id == :org AND acl_read && :principals`. 도우미 함수 하나(`visible_pages`)로 모아 둔다. 원시 SQL 에서도 같은 두 조건.
- **감사 기록:** 상태를 바꾸는 문(approve·discard·purge·acl)은 `audit_log` 1행을 **같은 트랜잭션**에 남긴다. 요청 기록(`request_log`)은 반대로 **다른 트랜잭션**에 남긴다(409·422 가 롤백돼도 기록은 남게).
- **Alembic:** async `env.py`, `target_metadata` 는 `import <pkg>.models` 한 줄로. 마이그레이션 URL 은 환경 변수 하나만 읽고 폴백 없음. `compare_type`·`compare_server_default` 켬. 리비전 id 는 손으로(`0001`, `0002` …). 위험한 DDL 앞에는 `SET LOCAL lock_timeout = '5s'` 와 위반 행을 세는 `DO $$ … RAISE EXCEPTION` 가드.
- **스키마가 여럿이면 트리도 여럿.** BHQ 는 `alembic/`(public) · `alembic_account/` · `alembic_messenger/`. 각 트리는 자기 스키마에 버전 표를 두고(`version_table_schema`), `configure` 앞에서 `CREATE SCHEMA IF NOT EXISTS`.

**발췌 — Base** (`src/bhq/models/base.py`, 줄임)

```python
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict] = {datetime: DateTime(timezone=True)}
```

### 3.3 설정

- `pydantic-settings` 의 `Settings` 하나. 환경 변수 이름 = 필드 이름(대문자). `@cache get_settings()` 로 한 번만 읽고, 시험은 `get_settings.cache_clear()`.
- **꼭 필요한 값**은 기본값 `None` → 쓰는 쪽이 이름을 대며 실패(예: DB 주소가 없으면 엔진이 RuntimeError, 워커는 종료 코드 2).
- **없어도 되는 기능**은 `*_missing` 속성이 빠진 **키 이름만** 돌려준다 → 그 기능만 503 으로 꺼지고 앱은 뜬다.
- 범위·모양은 `field_validator` 로 **기동 때** 막는다. 고르는 값은 `Literal`(오타가 조용히 `off` 가 되지 않게). 비밀은 `SecretStr`, 오류 문구에 값을 넣지 않는다.
- 코드 곳곳에서 `os.environ` 을 직접 읽지 않는다.

### 3.4 서비스·워커·LLM·관리 명령

- **워커:** 프로세스 하나에 `asyncio.gather(레인A, 레인B, 박동)`. 레인 하나가 죽으면 프로세스가 죽는다(재기동은 바깥 감시자가). SIGTERM 은 `stop` 이벤트만 세우고, 처리 중이던 일은 다음 기동이 이어 간다.
- **일감 큐 = Postgres 표.** 원자 집기는 `FOR UPDATE SKIP LOCKED` + `UPDATE … RETURNING`. 자동 재시도는 없다. 실패는 `failed_review` 로 가고 사람이 다시 넣는다(상한 3회). 오래 멈춘 일은 회수한다.
- **LLM 게이트웨이 한 곳.** 어느 모델을 쓸지는 코드가 아니라 등록 표가 정한다. 동시성 세마포어는 이벤트 루프마다 따로(루프에 묶이기 때문). 파싱·스키마 실패일 때만 정확히 1회 다시 부른다. 사용량은 원장 표에 남기고 커밋은 호출자가.
- **관리 명령** `python -m scripts.x`: **기본은 미리 보기**(끝까지 돈 뒤 ROLLBACK), `--apply` 일 때만 커밋. 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절. 결과 JSON 은 stdout, 안내는 stderr.

**발췌 — 큐 원자 집기** (`src/bhq/service/compile/queue.py`, 줄임)

```python
pick = (select(model.id).where(model.status == CLAIMABLE).order_by(model.id).limit(1)
        .with_for_update(skip_locked=True).scalar_subquery())
row = await session.execute(
    update(model).where(model.id == pick)
    .values(status=RUNNING, claimed_at=now_utc(), claimed_by=worker_id)
    .returning(model.id))
return row.scalar_one_or_none()
```

### 3.5 시험

| 폴더 | 무엇 | DB |
|---|---|---|
| `tests/unit/` | 순수 로직·경계 대조 | 없음 |
| `tests/integration/` | crud·service·마이그레이션 | 라이브 PG |
| `tests/contracts/` | 진짜 `create_app()` 을 `httpx.ASGITransport` 로 부른다. 회사 둘로 경계 확인 | 라이브 PG |

- **세션마다 한 번** `alembic downgrade base → upgrade head`(head 가 1개인지도 본다). 스위트마다 따로 돌리면 서로의 자료를 지운다.
- **시험마다** 연결 하나 + 바깥 트랜잭션, 끝에 롤백. ORM 세션은 `join_transaction_mode="create_savepoint"` 로 합류.
- **계약 시험은 `db()` 의존성을 바꿔치기하지 않는다.** 트랜잭션 경계 자체가 시험 대상이다. 앱의 `session_factory` 만 그 연결에 묶는다. lifespan 은 돌리지 않는다.
- DB 주소(`<PKG>_TEST_DATABASE_URL`)가 없으면 `pytest.fail`. skip 하면 초록이 거짓말이 된다.
- `tests/stale_patch_guard.py`: 재노출 껍데기를 `monkeypatch` 하면 시험을 죽인다(거짓 초록 방지).
- 시험 폴더에 `__init__.py` 가 없으니 **파일 이름(basename)이 폴더끼리 겹치면 안 된다.** 자식 프로세스를 띄우는 시험은 `PYTHONPATH` 를 시험이 직접 준다.
- 픽스처 자료: IP 는 `192.0.2.0/24`, 회사는 A사·B사, 고객사 실명·도메인 금지.

---

## 4. 품질 관문 `make verify`

```
editable-check → gate → lint → lint-imports → test
```

| 단계 | 하는 일 | 왜 |
|---|---|---|
| `editable-check` | **저장소 밖**(`cd $HOME`)에서 `import <pkg>` | pytest 는 `pythonpath` 로 원본을 봐서 편집 설치가 죽어도 모른다 |
| `gate` (`scripts/gate.sh`) | 금지 의존성 import · requirements 행 · IP 리터럴 · 회사 도메인 · 파일 크기 · 패키징 · 비밀 | 결정론 검사. 실패를 모아 마지막에 `exit 1` |
| `lint` | `ruff check .` (BHQ 설정은 `extend-exclude` 한 줄, 나머지 기본값) | |
| `lint-imports` | import-linter 계약 | §2 아파트 규칙 |
| `test` | `pytest` (`pythonpath=["src","."]`, `asyncio_mode="auto"`) | 라이브 PG 필요 |

**발췌 — Makefile** (BHQ `Makefile`, 줄임. 들여쓰기는 탭)

```make
install:
	$(BIN)/pip install -r requirements.txt -r requirements-dev.txt
	$(BIN)/pip install --no-deps -e .
	@command -v chflags >/dev/null 2>&1 && chflags -R nohidden $(VENV) || true
lock:
	$(BIN)/pip-compile --strip-extras -o requirements.txt requirements.in
	$(BIN)/pip-compile --strip-extras -o requirements-dev.txt requirements-dev.in
editable-check:
	@cd $(HOME) && $(CURDIR)/$(BIN)/python -c "import bhq" >/dev/null 2>&1 \
	  || { echo "미구성: 편집 설치가 죽었습니다 — make install"; exit 1; }
verify:
	@command -v chflags >/dev/null 2>&1 && chflags -R nohidden $(VENV) 2>/dev/null || true
	@$(MAKE) editable-check
	@$(MAKE) gate
	@$(MAKE) lint
	@$(MAKE) lint-imports
	@$(MAKE) test
```

**같은 검사를 세 군데서:** `make verify`(사람·에이전트) · `.githooks/pre-push`(gate + lint-imports + 훅 회귀) · CI(push 마다 gates 잡 + test 잡). 셋이 **같은 스크립트**를 부른다. 훅·CI·에이전트 규칙의 자세한 틀은 SDLC 안내서 §6 에 있다.

---

## 5. 옮기는 순서

각 단계 끝에 `make verify` 가 초록이어야 다음으로 간다.

1. **도구:** 패키지 이름 `<pkg>` 를 정하고 `pyproject.toml` · `requirements.in` · `requirements-dev.in` · `Makefile` 을 옮긴다. `make venv install` → `make editable-check` 통과.
2. **뼈대와 경계:** §2 폴더를 만들고 import-linter 계약 ①·③ 만 넣는다(②는 구성요소가 둘 이상 생길 때).
3. **설정·DB:** `core/config.py`(Settings) · `database/session.py` · `models/base.py` · `alembic/env.py` · 첫 리비전 `0001`.
4. **HTTP:** `main.py`(create_app + lifespan) · `app/{deps,errors,routers,middleware}.py` · `GET /v1/health` 하나 + 계약 시험 하나.
5. **시험 하네스:** `tests/conftest.py`(세션 1회 마이그레이션 왕복) · integration/contracts conftest(바깥 트랜잭션 + savepoint) · `stale_patch_guard.py`.
6. **관문:** `scripts/gate.sh`(금지 의존성·IP·도메인·비밀) · `check_file_size.py` · `.githooks/pre-push` · CI.
7. **필요해지면:** 워커·큐 표(§3.4), LLM 게이트웨이, 관리 명령 틀, 두 번째 앱(발급소처럼 다른 경계를 가진 앱은 errors·deps 를 따로 두고 공용은 `core` 에만).

---

## 6. 옮길 때 바꿀 BHQ 고유 자리

- 패키지 이름 `bhq`·`bhq-core`, 환경 변수 접두 `BHQ_`, DB 롤 이름(`bhq_api`·`bhq_worker` …), 시험 회사 slug.
- import-linter 계약 ②(BHQ 구성요소 목록)와 ④~⑥(계정·메신저 경계). 일반 패턴으로는 ①·③ 만 가져간다.
- `gate.sh` 의 회사 도메인 정규식, `check_endpoints.py` 의 인증 별칭 이름.
- `deps.py` 의 `Caller` 칸(area_slug·channel 등)과 JWT·앱 토큰 갈래, 개발용 별명 키.
- `visible_pages` 안의 `Page`·`status == 'active'` → 자기 자원 표로 일반화.
- 청크 표 동적 DDL(HNSW·trgm), `idx` 스키마 — 벡터 검색이 없으면 통째로 뺀다.
- LLM `claude_code` 어댑터(구독 CLI 전제). API 키를 쓰면 공식 SDK 어댑터로 바꾼다.
- 도메인 전용 의존성(PDF·HWP 추출, OIDC·MFA 라이브러리 등).

---

## 7. 함정 (BHQ 실측)

1. **macOS 숨김 `.pth`.** Python 3.13 이상은 hidden 플래그가 붙은 `.pth` 를 건너뛴다. iCloud 폴더면 몇 분 안에 다시 숨긴다 → 편집 설치가 조용히 죽는다. `make install`·`verify` 가 `chflags -R nohidden .venv` 를 먼저 돌리고, `editable-check` 가 저장소 밖에서 잰다.
2. **worktree 의 `.venv` 링크.** 링크한 `.venv` 의 편집 설치는 원래 폴더의 `src` 를 가리킨다. pytest 밖에서 `import` 하면 다른 가지 코드가 잡힌다 → `PYTHONPATH=<worktree>/src`.
3. **forbidden 계약의 빈틈.** import-linter `forbidden` 은 source 와 겹치는 짝을 건너뛰고, 짝 없는 `ignore_imports` 는 실행을 죽인다. "이 모듈은 이 무리만 부른다"는 `protected` 로.
4. **package-data 글롭이 0장이어도 조용하다.** 휠에 JSON 스키마가 0장 실린 적이 있다 → 비-.py 파일이 글롭에 맞는지 검사(`check_packaging.py`).
5. **uvicorn 은 루트 로거를 비워 둔다.** `basicConfig` 를 lifespan 안에서 부르지 않으면 INFO 가 0줄이다(모듈 최상위에 두면 pytest 캡처와 섞인다).
6. **계약 시험은 lifespan 을 안 돈다.** `app.state` 에 넣는 캐시는 `create_app()` 안에서 만든다. lifespan 에만 두면 시험에서 500.
7. **GZip 제외 목록은 기본값에 더한다.** 덮어쓰면 `text/event-stream` 이 빠져 SSE 가 압축된다.
8. **yield 의존성은 응답을 보낸 뒤 닫힌다.** 커밋이 응답 뒤로 밀려, 302 를 따라온 다음 요청이 방금 쓴 것을 못 봤다 → `Depends(db, scope="function")` 또는 응답 전 명시 `commit`.
9. **FastAPI 0.141 의 포함 라우터.** `include_router` 한 라우터가 게으른 `_IncludedRouter` 로 담겨 `app.routes` 에 APIRoute 가 0개로 보인다 → 경로는 openapi `paths` 로 센다. 사용자 정의 `route_class` 는 `handle` 을 감싼다.
10. **`asyncio.Semaphore` 는 처음 경합한 루프에 묶인다.** 다른 루프에서 쓰면 죽는다 → 루프마다 따로(`weakref`).
11. **`onupdate` 는 ORM 에서만 돈다.** 원시 UPDATE 에서는 `updated_at` 을 코드가 직접 넣는다.
12. **`alembic check` 는 CHECK 제약과 FK 이름을 비교하지 않는다.** 그런 변경은 라이브 DB 시험으로 잰다.
13. **`pydantic.ValidationError` 를 전역 처리기에 걸지 않는다.** 응답 모델 버그까지 422 가 되어 서버 버그가 손님 잘못처럼 보인다.
14. **`env.py` 가 둘 이상이면 mypy 가 `Duplicate module named "env"` 로 검사 전에 죽는다.** BHQ 는 mypy 를 관문에 넣지 않았다.

---

## 8. 조사하다 찾은 "문서와 코드가 다른 곳" (BHQ 쪽 고칠 거리)

다른 프로젝트에 옮길 때는 **코드 쪽**을 따른다.

| 문서·주석의 말 | 실제 코드 |
|---|---|
| CLAUDE.md: crud 는 `CRUDBase` 를 상속 | 아무도 상속하지 않는다. 실제 모양은 `session` 을 첫 인자로 받는 모듈 함수 |
| CLAUDE.md: LLM 은 공식 SDK(openai·anthropic) | `openai` 패키지는 requirements 에 없다. OpenAI 호환은 httpx 직접, Claude 는 `claude-agent-sdk` |
| CI 단계 이름: import 계약 "3건" | 실제 7건 |
| Makefile `verify` 주석: gate → editable | 실제 순서는 editable-check → gate |
| (암묵) 인증 없는 `/v1` 라우트 검사가 관문에 있다 | `check_endpoints.py` 는 gate·verify 에 없다. 계약 시험 하나와 CI 픽스처 시험에서만 돈다 |
| audit 헬퍼는 하나 | 두 벌(`crud/audit.insert` · `crud/activity.insert_audit`). 옮길 때는 하나로 |

---

# Resources

BHQ backend (`bctone1/BHQ_backend`, `origin/main` `2e79c0e`) 안의 원본. 경로는 저장소 뿌리 기준.

- 스택·도구: `.python-version` · `requirements.in` · `requirements-dev.in` · `pyproject.toml`(import-linter 계약 52~402행, pytest 404~407행, ruff 409~411행) · `Makefile`
- 관문: `scripts/gate.sh` · `scripts/check_file_size.py` · `scripts/check_packaging.py` · `scripts/check_secrets.sh` · `scripts/check_endpoints.py` · `.githooks/pre-push` · `.github/workflows/ci.yml`
- 진입점·HTTP: `src/bhq/main.py` · `src/bhq/app/{routers,deps,errors,middleware}.py` · `src/bhq/app/endpoints/decision_candidates.py`(목록 GET + 상태 변경 POST 예) · `src/bhq/core/pagination.py`
- 데이터: `src/bhq/database/session.py` · `src/bhq/models/base.py` · `src/bhq/crud/base.py` · `src/bhq/crud/audit.py` · `alembic/env.py` · `alembic/versions/0010_same_org_fk.py`(가드·lock_timeout 예)
- 설정·서비스: `src/bhq/core/config.py` · `src/bhq/service/llm/gateway.py` · `src/bhq/service/compile/queue.py` · `src/bhq/worker.py` · `scripts/bind_runtime.py`(관리 명령 틀)
- 시험: `tests/conftest.py` · `tests/integration/conftest.py` · `tests/contracts/conftest.py` · `tests/stale_patch_guard.py`
- 에이전트 규칙: `CLAUDE.md`(종류 → 위치 표, 파일 크기 표, Things Claude gets wrong)
