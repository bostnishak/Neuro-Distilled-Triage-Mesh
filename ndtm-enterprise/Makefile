# ==============================================================================
# Neuro-Distilled Triage Mesh (NDTM) — Enterprise Automation Makefile
# ==============================================================================

.PHONY: help init up down restart logs ps test test-unit test-sec distill chaos-up clean certify-100

SHELL := /bin/bash
DOCKER_COMPOSE := docker compose
PYTHON := python

help:
	@echo "================================================================================"
	@echo "NDTM Enterprise Core Command Matrix"
	@echo "================================================================================"
	@echo "  make init          - Bootstrap local environment files and directories"
	@echo "  make up            - Build and launch all 10 production containers in background"
	@echo "  make down          - Stop and destroy all containers, networks, and volumes"
	@echo "  make restart       - Restart backend and worker services"
	@echo "  make logs          - Follow live aggregated container logs"
	@echo "  make ps            - Inspect status and health of the container cluster"
	@echo "  make test          - Run complete automated pytest suite across all modules"
	@echo "  make test-sec      - Run AppSec penetration tests (PII, injection, rate limit)"
	@echo "  make distill       - Run offline logit distillation and ONNX INT8 quantization"
	@echo "  make chaos-up      - Launch cluster with Toxiproxy fault-injection overlay"
	@echo "  make certify-100   - Run 7-Gate Master Zero-Defect Certification Orchestrator"
	@echo "  make clean         - Purge cache files, compiled bytecodes, and temp assets"
	@echo "================================================================================"

init:
	@test -f .env || cp .env.example .env
	@mkdir -p distilled_models infra/postgres infra/rabbitmq infra/prometheus infra/nginx
	@echo "[+] Initialization complete. Generated .env and runtime directories."

up: init
	$(DOCKER_COMPOSE) up --build -d
	@echo "[+] NDTM Enterprise cluster running. Web Cockpit at http://localhost"

down:
	$(DOCKER_COMPOSE) down -v --remove-orphans
	@echo "[+] NDTM Enterprise cluster stopped and cleaned."

restart:
	$(DOCKER_COMPOSE) restart backend outbox-relay triage-consumer shadow-consumer
	@echo "[+] Application services restarted."

logs:
	$(DOCKER_COMPOSE) logs -f --tail=100

ps:
	$(DOCKER_COMPOSE) ps

test:
	$(DOCKER_COMPOSE) exec -T backend pytest backend/tests -v --durations=10

test-unit:
	$(PYTHON) -m pytest backend/tests -v -k "not test_deduplication_sql"

test-sec:
	$(DOCKER_COMPOSE) exec -T backend pytest backend/tests/test_pii_and_security.py -v

distill:
	@echo "[*] Triggering DistillMesh logit distillation and ONNX INT8 quantization..."
	$(PYTHON) -m ml_pipeline.onnx_exporter

chaos-up: init
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.chaos.yml up --build -d
	@echo "[+] Chaos Engineering overlay activated with Toxiproxy."

certify-100:
	@echo "[*] Executing NDTM Master Zero-Defect Certification Orchestrator..."
	@bash scripts/run_full_certification.sh

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name "dist" -exec rm -rf {} +
	@echo "[+] Workspace cleaned."
