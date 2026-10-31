# Common entry points. CLAUDE.md documents when to use each one.
.DEFAULT_GOAL := help
.PHONY: help install lint format test check run terraform-check bootstrap plan apply

# Terraform roots live under infra/terraform/envs/<ENV>. ENV is dev or prod.
ENV ?= dev
TF ?= terraform
TF_DIR := infra/terraform
TF_ROOT := $(TF_DIR)/envs/$(ENV)
TF_INIT := $(TF) -chdir=$(TF_ROOT) init -input=false -backend-config=backend.tfvars

# A Claude Code session has a short-lived token in CLOUDSDK_AUTH_ACCESS_TOKEN
# and no key file. Hand the same token to the Google provider and the GCS
# backend. Outside a session this is unset and Terraform falls back to
# Application Default Credentials.
ifneq ($(CLOUDSDK_AUTH_ACCESS_TOKEN),)
export GOOGLE_OAUTH_ACCESS_TOKEN ?= $(CLOUDSDK_AUTH_ACCESS_TOKEN)
endif

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install: ## Install the locked dependencies, including the dev group
	uv sync --locked

lint: ## Lint and check formatting without changing files
	uv run ruff check .
	uv run ruff format --check .

format: ## Fix lint issues and reformat
	uv run ruff check --fix .
	uv run ruff format .
	$(TF) fmt -recursive $(TF_DIR)

test: ## Run the unit tests
	uv run pytest

terraform-check: ## terraform fmt -check and validate on every root, no cloud access needed
	$(TF) fmt -check -recursive -diff $(TF_DIR)
	@for env in dev prod; do \
		echo "== validate envs/$$env"; \
		$(TF) -chdir=$(TF_DIR)/envs/$$env init -input=false -backend=false >/dev/null && \
		$(TF) -chdir=$(TF_DIR)/envs/$$env validate || exit 1; \
	done

check: lint test terraform-check ## Everything CI runs

run: ## Serve the app locally on http://127.0.0.1:8080
	uv run uvicorn app.main:app --reload --port 8080

bootstrap: ## Create the Terraform state bucket for ENV once, with gcloud. Safe to rerun
	@bucket=$$(sed -n 's/^bucket *= *"\(.*\)"/\1/p' $(TF_ROOT)/backend.tfvars); \
	project=$$(sed -n 's/^project_id *= *"\(.*\)"/\1/p' $(TF_ROOT)/terraform.tfvars); \
	region=$$(sed -n 's/^region *= *"\(.*\)"/\1/p' $(TF_ROOT)/terraform.tfvars); \
	echo "state bucket gs://$$bucket in $$project ($$region)"; \
	gcloud storage buckets describe "gs://$$bucket" --project="$$project" >/dev/null 2>&1 || \
		gcloud storage buckets create "gs://$$bucket" --project="$$project" --location="$$region" \
			--uniform-bucket-level-access --public-access-prevention; \
	gcloud storage buckets update "gs://$$bucket" --project="$$project" --versioning

plan: ## terraform plan for ENV=dev|prod. Runs freely
	$(TF_INIT)
	$(TF) -chdir=$(TF_ROOT) plan -input=false -lock-timeout=60s

apply: ## terraform apply for ENV=dev|prod. Prod additionally needs CONFIRM=prod
ifeq ($(ENV),prod)
	@test "$(CONFIRM)" = "prod" || { echo "Refusing to apply to prod without CONFIRM=prod and the owner's go-ahead."; exit 1; }
endif
	$(TF_INIT)
	$(TF) -chdir=$(TF_ROOT) plan -input=false -lock-timeout=60s -out=plan.tfplan
	$(TF) -chdir=$(TF_ROOT) apply -input=false -lock-timeout=60s plan.tfplan
	@rm -f $(TF_ROOT)/plan.tfplan
