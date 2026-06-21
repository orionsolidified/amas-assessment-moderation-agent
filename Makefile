.PHONY: generate validate test secrets up down logs migrate prompts workflows policies demo evals redteam backup existing-env-install

generate:
	python3 scripts/generate_workflows.py

validate: generate
	python3 scripts/validate_bundle.py

test:
	pytest -q

secrets:
	python3 scripts/generate_secrets.py

up:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d postgres garage n8n intake-api

down:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml down

logs:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f --tail=200

migrate:
	./scripts/apply_migrations.sh

prompts:
	docker compose --env-file deploy/.env -f deploy/docker-compose.yml run --rm bootstrap

workflows:
	./scripts/import_workflows.sh

policies:
	python3 scripts/ingest_demo_policies.py

demo:
	./scripts/submit_demo.sh

evals:
	./scripts/run_evals.sh

redteam:
	./scripts/run_redteam.sh

backup:
	./scripts/backup.sh

existing-env-install:
	sudo ./scripts/amas_env_manager.sh install
