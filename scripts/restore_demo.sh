#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${1:?Usage: restore_demo.sh BACKUP_DIR}"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"
[[ -f "$BACKUP_DIR/amas-postgres.dump" ]] || { echo "Missing database dump" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a
cat >&2 <<'WARN'
WARNING: This demonstration restore overwrites the configured PostgreSQL database and Garage volume.
Set CONFIRM_RESTORE=YES to continue.
WARN
[[ "${CONFIRM_RESTORE:-}" == YES ]] || exit 2

docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" up -d postgres garage
cat "$BACKUP_DIR/amas-postgres.dump" | docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists
if [[ -f "$BACKUP_DIR/garage-data.tgz" ]]; then
  docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" stop garage
  cat "$BACKUP_DIR/garage-data.tgz" | docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
    run --rm --entrypoint sh garage -lc 'rm -rf /var/lib/garage/* && tar -C /var/lib/garage -xzf -'
  docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" start garage
fi
