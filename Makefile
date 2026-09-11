.PHONY: install test lint typecheck check

install:
	pip install -e ".[dev]"

test:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check .

typecheck:
	mypy app

check: lint typecheck test
