.PHONY: setup start stop reset generate-data import-data seed analyze-graph detect-fraud evaluate test lint typecheck format benchmark

setup:
	cp -n .env.example .env || true
	cd backend && python -m venv .venv
	cd backend && .venv/Scripts/pip install -r requirements.txt || .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

start:
	docker compose up --build

stop:
	docker compose down

reset:
	cd backend && python scripts/reset_database.py

generate-data:
	cd backend && python scripts/generate_dataset.py --customers 5000 --accounts 7000 --transactions 50000 --fraud-rate 0.03 --seed 42

import-data:
	cd backend && python scripts/import_dataset.py --data-dir ../data/generated

seed: generate-data import-data

analyze-graph:
	cd backend && python scripts/run_graph_analytics.py

detect-fraud: analyze-graph
	cd backend && python scripts/run_fraud_detection.py

evaluate:
	cd backend && python scripts/evaluate_detection.py

test:
	cd backend && pytest -v

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && mypy app/ --ignore-missing-imports

format:
	cd backend && ruff format .

benchmark:
	cd backend && python scripts/benchmark.py
