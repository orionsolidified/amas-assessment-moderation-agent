#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a

for file in "$ROOT"/sql/*.sql; do
  echo "Applying $(basename "$file")"
  docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
    exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$file"
done

docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --set=amas_app_password="$AMAS_APP_PASSWORD" \
  --set=amas_readonly_password="$AMAS_READONLY_PASSWORD" <<'SQL'
ALTER ROLE amas_app PASSWORD :'amas_app_password';
ALTER ROLE amas_readonly PASSWORD :'amas_readonly_password';
SQL
