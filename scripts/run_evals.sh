#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env}"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a
export AMAS_EVAL_WEBHOOK_URL="${AMAS_EVAL_WEBHOOK_URL:-${WEBHOOK_URL%/}/webhook/amas/eval/moderate}"
cd "$ROOT/evals"
if command -v promptfoo >/dev/null 2>&1; then
  promptfoo eval -c promptfooconfig.yaml --no-cache --output results.json
else
  npx --yes promptfoo@latest eval -c promptfooconfig.yaml --no-cache --output results.json
fi
