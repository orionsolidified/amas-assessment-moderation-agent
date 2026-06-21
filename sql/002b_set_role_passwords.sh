#!/usr/bin/env bash
set -Eeuo pipefail
: "${AMAS_APP_PASSWORD:?AMAS_APP_PASSWORD is required}"
: "${AMAS_READONLY_PASSWORD:?AMAS_READONLY_PASSWORD is required}"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=amas_app_password="$AMAS_APP_PASSWORD" \
  --set=amas_readonly_password="$AMAS_READONLY_PASSWORD" <<'SQL'
ALTER ROLE amas_app PASSWORD :'amas_app_password';
ALTER ROLE amas_readonly PASSWORD :'amas_readonly_password';
SQL
