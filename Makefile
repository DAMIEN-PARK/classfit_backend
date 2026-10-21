# BCTONE 강사관리 플랫폼 백엔드 — 패키지 classfit (임시 이름)
# 품질 관문: make verify = editable-check → gate → lint → lint-imports → test
PY ?= python3.14
# iCloud(~/Documents) 는 *.nosync 폴더를 동기화하지 않는다. 실제 venv 는 .venv.nosync 에 두고 .venv 는 심볼릭 링크다.
# (iCloud 가 동기화한 .pth 에 숨김 플래그를 붙이면 Python 3.13+ 이 건너뛰어 편집 설치가 조용히 죽는다.)
VENV_REAL ?= .venv.nosync
VENV ?= .venv
BIN := $(VENV)/bin
PKG := classfit
PG_BIN ?= /opt/homebrew/opt/postgresql@17/bin
# .env 가 있으면 그 값으로 명령을 감싼다. 셸 환경이 .env 보다 우선한다(pydantic-settings 와 같은 순서).
ENVRUN := $(if $(wildcard .env),$(BIN)/python -m dotenv --file .env run --no-override --,)

.PHONY: venv install lock unhide editable-check gate lint lint-imports test verify hooks fix-start fix-end db-create migrate run

venv:
	$(PY) -m venv $(VENV_REAL)
	@[ -e $(VENV) ] || ln -s $(VENV_REAL) $(VENV)
	$(BIN)/pip install --upgrade pip pip-tools

$(BIN)/pip:
	@$(MAKE) venv

install: $(BIN)/pip
	$(BIN)/pip install -r requirements.txt -r requirements-dev.txt
	$(BIN)/pip install --no-deps -e .
	@$(MAKE) unhide

lock: $(BIN)/pip
	$(BIN)/pip-compile --strip-extras -o requirements.txt requirements.in
	$(BIN)/pip-compile --strip-extras -o requirements-dev.txt requirements-dev.in

# 숨김 플래그가 붙은 .pth 를 푼다. 패키지를 import 하는 타깃은 전부 이걸 먼저 거친다.
unhide:
	@command -v chflags >/dev/null 2>&1 && [ -d $(VENV_REAL) ] && chflags -R nohidden $(VENV_REAL) 2>/dev/null || true

# 저장소 밖에서 import 해 본다. pytest 는 pythonpath 로 원본을 봐서 편집 설치가 죽어도 모른다.
editable-check: unhide
	@cd $(HOME) && $(CURDIR)/$(BIN)/python -c "import $(PKG)" >/dev/null 2>&1 \
	  || { echo "미구성: 편집 설치가 죽었습니다 — make install"; exit 1; }

gate:
	bash scripts/gate.sh

lint:
	$(BIN)/ruff check .

lint-imports: unhide
	$(BIN)/lint-imports

test: unhide
	$(ENVRUN) $(BIN)/pytest

verify:
	@$(MAKE) editable-check
	@$(MAKE) gate
	@$(MAKE) lint
	@$(MAKE) lint-imports
	@$(MAKE) test

hooks:
	git config core.hooksPath .githooks
	git config merge.ff false

fix-start:           ## 버그 픽스 모드 on (tests/** 편집을 훅이 차단)
	@mkdir -p .claude && touch .claude/fix-mode && echo "fix-mode ON"

fix-end:             ## 버그 픽스 모드 off
	@rm -f .claude/fix-mode && echo "fix-mode OFF"

# 공유 Postgres 17 인스턴스에 이 프로젝트용 DB 두 개만 만든다 (서비스 설정은 건드리지 않는다)
db-create:
	@for db in classfit_dev classfit_test; do \
	  if [ "$$($(PG_BIN)/psql -d postgres -Atc "select 1 from pg_database where datname='$$db'")" = "1" ]; then \
	    echo "$$db: 이미 있음"; \
	  else \
	    $(PG_BIN)/createdb "$$db" && echo "$$db: 생성"; \
	  fi; \
	done

migrate: unhide
	$(ENVRUN) $(BIN)/alembic upgrade head

run: unhide
	$(ENVRUN) $(BIN)/uvicorn $(PKG).main:app --reload --port 8000
