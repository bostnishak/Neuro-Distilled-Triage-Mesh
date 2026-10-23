# ==============================================================================
# NEURO-DISTILLED TRIAGE MESH (NDTM-9000) — MASTER AUTOMATION MAKEFILE
# ==============================================================================

.PHONY: help init up down restart logs ps build test test-unit test-cpp test-sec distill genesis chaos-up clean certify

SHELL := /bin/bash
DOCKER_COMPOSE := docker compose
PYTHON := python

help:
	@echo "================================================================================"
	@echo "NDTM-9000 SOVEREIGN KERNEL — OPERATING SYSTEM COMMAND MATRIX"
	@echo "================================================================================"
	@echo "  make init          - Bootstrap local directories, generate .env from template"
	@echo "  make genesis       - Execute deterministic genesis bootstrapper (keys, seed, ONNX)"
	@echo "  make up            - Build and launch all 11 production services in background"
	@echo "  make down          - Gracefully stop and clean all containers, networks, volumes"
	@echo "  make restart       - Restart backend kernel and distributed workers"
	@echo "  make logs          - Follow live aggregated container log streams"
	@echo "  make ps            - Inspect health and runtime status of the cluster"
	@echo "  make build         - Recompile C++20 edge daemon, Python kernel, and Vite cockpit"
	@echo "  make test          - Run complete automated pytest verification suite in container"
	@echo "  make test-unit     - Run local unit tests (DSL, Hawkes, PID, Z3, Causal, Krum)"
	@echo "  make test-cpp      - Compile and run C++20 Lock-Free Ring Buffer & FFT tests"
	@echo "  make test-sec      - Run AppSec penetration tests (JWT, RBAC, PromptGuard, HITL)"
	@echo "  make distill       - Trigger contrastive + KL logit distillation & INT8 quantization"
	@echo "  make chaos-up      - Launch cluster with Toxiproxy network fault injection"
	@echo "  make certify       - Execute Master 24-Phase Zero-Defect Certification Orchestrator"
	@echo "  make clean         - Purge cache files, compiled binaries, and temporary assets"
	@echo "================================================================================"

init:
	@test -f .env || cp .env.example .env
	@mkdir -p models distilled_models infra/postgres infra/rabbitmq infra/redis/lua_scripts infra/prometheus infra/nginx
	@echo "[+] Initialization complete. Generated .env and runtime directories."

genesis: init
	@echo "[*] Bootstrapping deterministic Genesis Engine (topology, Ed25519 keys, baseline INT8 model)..."
	$(PYTHON) -m backend.bootstrap.genesis

up: init
	$(DOCKER_COMPOSE) up --build -d
	@echo "[+] NDTM-9000 Sovereign Kernel running. Cockpit available at http://localhost"

down:
	$(DOCKER_COMPOSE) down -v --remove-orphans
	@echo "[+] NDTM-9000 Sovereign Kernel cluster stopped and pruned."

restart:
	$(DOCKER_COMPOSE) restart backend triage-pipeline-worker shadow-drift-worker distillation-forge-worker
	@echo "[+] Kernel and background workers restarted."

logs:
	$(DOCKER_COMPOSE) logs -f --tail=100

ps:
	$(DOCKER_COMPOSE) ps

build:
	$(DOCKER_COMPOSE) build

test:
	$(DOCKER_COMPOSE) exec -T backend pytest backend/tests -v --durations=10

test-unit:
	$(PYTHON) -m pytest backend/tests -v

test-cpp:
	@echo "[*] Compiling and running C++20 Edge Kernel Invariant Tests..."
	@g++ -std=c++20 -O3 -Iedge_cpp_kernel/include \
		edge_cpp_kernel/src/shm_zero_copy_arena.cpp \
		edge_cpp_kernel/src/radix2_fft_spectrogram.cpp \
		edge_cpp_kernel/src/laplacian_simd_optics.cpp \
		edge_cpp_kernel/tests/test_cpp_kernel_invariants.cpp \
		-o test_cpp_kernel_invariants.exe
	@./test_cpp_kernel_invariants.exe
	@rm -f test_cpp_kernel_invariants.exe

test-sec:
	$(PYTHON) -m pytest backend/tests/test_06_redteam_security_pentest.py -v

distill:
	@echo "[*] Initiating Contrastive + KL Distillation & INT8 Quantization Forge..."
	$(PYTHON) -m backend.ml_forge.contrastive_kl_distiller

chaos-up: init
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.chaos.yml up --build -d
	@echo "[+] Chaos Engineering overlay activated with Toxiproxy."

certify:
	@echo "[*] Executing NDTM-9000 Sovereign Certification Harness..."
	@bash scripts/run_sovereign_certification.sh

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name "dist" -exec rm -rf {} +
	@rm -f *.exe *.o
	@echo "[+] Workspace cleaned."
