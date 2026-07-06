.PHONY: help install dev init docker-sqlite docker-mysql docker-prod docker-down logs health lint test

help:
	@echo "Targets:"
	@echo "  make install       - venv + pip install"
	@echo "  make dev           - uvicorn --reload :8808"
	@echo "  make init          - python scripts/init_data.py"
	@echo "  make docker-sqlite - compose profile sqlite"
	@echo "  make docker-mysql  - compose profile mysql"
	@echo "  make docker-prod   - compose profile prod + mysql"
	@echo "  make docker-down   - stop all compose services"
	@echo "  make health        - curl /api/health"
	@echo "  make test          - pytest"

PIP_MIRROR ?= tsinghua

install:
	python3 -m venv .venv
	PIP_MIRROR=$(PIP_MIRROR) PYTHON=.venv/bin/python sh scripts/docker-pip-install.sh

dev: init
	.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8808 --reload

init:
	.venv/bin/python scripts/init_data.py

docker-sqlite:
	docker compose --profile sqlite up -d --build

docker-mysql:
	docker compose --profile mysql up -d --build

docker-prod:
	docker compose --profile prod --profile mysql up -d --build

docker-down:
	docker compose --profile sqlite --profile mysql --profile prod down

logs:
	docker compose logs -f

health:
	curl -fsS http://127.0.0.1:$${PORT:-8808}/api/health && echo

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/python -m compileall -q src
