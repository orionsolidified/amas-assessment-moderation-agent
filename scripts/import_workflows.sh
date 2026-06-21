#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CONTAINER=${N8N_CONTAINER_NAME:-amas-n8n}
PROJECT_ID_ARG=""
if [ -n "${N8N_PROJECT_ID:-}" ]; then
  PROJECT_ID_ARG="--projectId=${N8N_PROJECT_ID}"
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
for file in "$PROJECT_ROOT"/workflows/[0-9][0-9]_*.json; do
  cp "$file" "$TMP_DIR/"
done

docker exec "$CONTAINER" rm -rf /tmp/amas-workflows
docker cp "$TMP_DIR/." "$CONTAINER:/tmp/amas-workflows"
# Imported workflows remain unpublished by design. Bind credentials, inspect, then publish deliberately.
docker exec -u node "$CONTAINER" n8n import:workflow --separate --input=/tmp/amas-workflows $PROJECT_ID_ARG
printf '%s\n' "Imported AMAS workflows as drafts. Bind named credentials, inspect each workflow, then publish the webhook workflows deliberately."
