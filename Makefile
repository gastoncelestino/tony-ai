# Makefile — convenience wrapper around docker/ and the test scripts.
# Nothing here is required — every target is a one-liner documented in
# docker/README.md / judgment-memory/README.md. Use directly if you'd
# rather not remember the flags.

COMPOSE := docker compose -f docker/docker-compose.yml

.PHONY: up up-gpu down down-clean logs ps verify verify-ledger verify-qdrant

up:            ## Start Ollama + Qdrant, pull embedding models
	$(COMPOSE) up -d
	$(COMPOSE) logs -f ollama-pull

up-gpu:        ## Same, with GPU passthrough for Ollama (see docker/README.md)
	docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
	$(COMPOSE) logs -f ollama-pull

down:          ## Stop containers, keep volumes (models/vectors persist)
	$(COMPOSE) down

down-clean:    ## Stop containers AND delete volumes (re-pulls everything next time)
	$(COMPOSE) down -v

logs:          ## Tail logs for both services
	$(COMPOSE) logs -f qdrant ollama

ps:            ## Show container + healthcheck status
	$(COMPOSE) ps

verify-ledger: ## Mock-based test — no services required
	python3 judgment-memory/test_ledger.py

verify-qdrant: ## Real smoke test against the containers started by `make up`
	bun run judgment-memory/scripts/verify-qdrant.ts

verify: verify-ledger verify-qdrant  ## Both test scripts, in order
