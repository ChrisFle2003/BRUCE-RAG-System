.PHONY: help setup build-all build-cpp build-python clean db-init up down run-all test benchmark import-docs eval-retrieval benchmark-backends

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
BIB_ID ?= 2000

help:
	@echo "BRUCE RAG System"
	@echo "make setup          - Install local Python dependencies into .venv"
	@echo "make build-cpp      - Configure and build C++ core (build/)"
	@echo "make build-python   - Validate Python package import graph"
	@echo "make build-all      - Build C++ and Python checks"
	@echo "make db-init        - Apply SQL schemas to PostgreSQL"
	@echo "make up             - Start local docker services"
	@echo "make down           - Stop local docker services"
	@echo "make test           - Run Python tests"
	@echo "make import-docs    - Import md/txt files into Knowledge DB"
	@echo "make eval-retrieval - Run retrieval MRR/Recall evaluation"
	@echo "make benchmark-backends - Compare extractive vs hf_api calc backend"
	@echo "make benchmark      - Run C++ benchmark mode"
	@echo "make clean          - Remove build artifacts"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r src/python/requirements.txt

build-cpp:
	mkdir -p build
	cd build && cmake .. && cmake --build . -j$$(nproc)

build-python:
	PYTHONPATH=src/python $(PYTHON) -m compileall src/python

build-all: build-cpp build-python

clean:
	rm -rf build logs .pytest_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

db-init:
	@echo "Initializing PostgreSQL schema..."
	PGPASSWORD=$${DB_PASSWORD:-secretpassword} psql \
		-v ON_ERROR_STOP=1 \
		-h $${DB_HOST:-localhost} \
		-p $${DB_PORT:-5432} \
		-U $${DB_USER:-bruce} \
		-d $${DB_NAME:-bruce_rag} \
		-f schema/00_knowledge_db.sql
	PGPASSWORD=$${DB_PASSWORD:-secretpassword} psql \
		-v ON_ERROR_STOP=1 \
		-h $${DB_HOST:-localhost} \
		-p $${DB_PORT:-5432} \
		-U $${DB_USER:-bruce} \
		-d $${DB_NAME:-bruce_rag} \
		-f schema/01_finish_db.sql

up:
	docker compose up -d

down:
	docker compose down

run-all: up

test:
	PYTHONPATH=src/python $(PYTHON) -c "import pytest" >/dev/null 2>&1 && \
		PYTHONPATH=src/python $(PYTHON) -m pytest -q || \
		PYTHONPATH=src/python $(PYTHON) -m unittest discover -s tests -p 'test_*.py'

benchmark:
	./build/bruce_core --benchmark

import-docs:
	-docker exec bruce_rag_project-api-1 sh -lc 'rm -rf /tmp/docs /tmp/import_docs.py'
	docker cp scripts/import_docs.py bruce_rag_project-api-1:/tmp/import_docs.py
	docker cp docs bruce_rag_project-api-1:/tmp/docs
	docker exec bruce_rag_project-api-1 sh -lc 'PYTHONPATH=/app/src/python python /tmp/import_docs.py /tmp/docs --bib-id $(BIB_ID)'

eval-retrieval:
	python3 scripts/eval_retrieval.py --api-base http://localhost:9998

benchmark-backends:
	python3 scripts/benchmark_backends.py --api-base http://localhost:9998 --project-root .
