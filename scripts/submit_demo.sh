#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"
if [[ -f "$ENV_FILE" ]]; then set -a; source "$ENV_FILE"; set +a; fi
BASE_URL="${AMAS_INTAKE_URL:-${AMAS_INTAKE_PUBLIC_URL:-http://localhost:8080}}"
: "${AMAS_API_TOKEN:?Set AMAS_API_TOKEN or create deploy/.env}"
curl --fail-with-body -sS \
  -H "X-AMAS-API-Token: $AMAS_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary "@$ROOT/samples/demo_case.json" \
  "$BASE_URL/v1/cases/json" | python3 -m json.tool
