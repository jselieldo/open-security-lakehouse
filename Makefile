.PHONY: install test lint config up down logs smoke ps

install:
	python3 -m venv .venv
	.venv/bin/pip install -r apps/api/requirements-dev.txt

test:
	.venv/bin/pytest -q --cov=app --cov-report=term-missing

lint:
	.venv/bin/ruff check apps/api/app tests

config:
	docker compose config --quiet

up:
	docker compose up --build --wait

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

smoke:
	set -a; . ./.env; set +a; ./scripts/smoke-test.sh

