#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a
OUT="${1:-$ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"

docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$OUT/amas-postgres.dump"
docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T garage tar -C /var/lib/garage -czf - . > "$OUT/garage-data.tgz"
docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.yml" \
  exec -T -u node n8n sh -lc 'rm -rf /tmp/amas-workflow-backup && n8n export:workflow --backup --output=/tmp/amas-workflow-backup' >/dev/null
docker cp amas-n8n:/tmp/amas-workflow-backup "$OUT/workflows"
cp "$ROOT/prompts/manifest.json" "$OUT/prompt-manifest.json"
sha256sum "$OUT"/* 2>/dev/null > "$OUT/SHA256SUMS" || true
printf 'Backup written to %s\n' "$OUT"
