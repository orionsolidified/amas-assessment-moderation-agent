#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run: python3 scripts/generate_secrets.py" >&2
  exit 2
fi
if grep -q 'CHANGE_ME' "$ENV_FILE"; then
  echo "Resolve all CHANGE_ME values in $ENV_FILE before continuing." >&2
  exit 2
fi
set -a; source "$ENV_FILE"; set +a

python3 "$ROOT/scripts/generate_workflows.py"
python3 "$ROOT/scripts/validate_bundle.py"

docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" up -d postgres garage n8n intake-api
until docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do sleep 2; done

"$ROOT/scripts/apply_migrations.sh"
docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" run --rm bootstrap
"$ROOT/scripts/import_workflows.sh"
cat <<'MSG'
AMAS infrastructure, database, prompts, and draft workflows are installed.
Next: create/bind the named n8n credentials, inspect workflows, publish them in docs/N8N_WORKFLOW_MAP.md order, then ingest the synthetic policies.
MSG
