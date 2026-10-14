lint:
	poetry run ruff check
lint-fix:
	poetry run ruff check --fix
lint-format:
	poetry run ruff format
format:
	poetry run make lint-fix
	poetry run make lint-format

init:
	poetry install
	@if [ ! -f .env ]; then cp .env.example .env; fi
	docker compose up -d
	make migrate

test-app:
	poetry run pytest -x --cov=app -vv
test-coverage:
	poetry run coverage html
test:
	make lint
	make test-app
	make test-coverage

test-file:
	@if [ -z "$(file)"]; then \
  		echo "Error: file variable is required. Usage: make test-file file=tests/app/domain/pokemon/test_service.py"; \
		exit 1; \
	fi
	poetry run pytest -s --cov=app --cov-report=html $(file)

dev:
	poetry run fastapi dev app/main.py

run:
	make dev

create-migration:
	@if [ -z "$(message)"]; then \
  		echo "Error: message variable is required. Usage: make create-migration message='Your migration message'"; \
		exit 1; \
	fi
	poetry run alembic revision --autogenerate -m "$(message)"

rollback-migration:
	poetry run alembic downgrade -1

migrate:
	poetry run alembic upgrade head

backup:
	poetry run python scripts/backup_database.py

restore-backup:
	poetry run python scripts/restore_database.py