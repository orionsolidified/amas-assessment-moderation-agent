#!/usr/bin/env bash
# AMAS environment installer and manager for an existing Docker Compose n8n deployment.
#
# The installer discovers the existing n8n Compose project, creates root-only AMAS
# environment files, injects only the AMAS subset through a Compose override, and
# recreates only the n8n execution services. It does not replace the existing n8n
# encryption key, database configuration, public routing, or user-management secrets.

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

VERSION="1.0.0"
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SOURCE_PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"

CONFIG_DIR="${AMAS_CONFIG_DIR:-/etc/amas}"
STATE_FILE=""
CANONICAL_ENV=""
N8N_ENV=""
PROMPTFOO_ENV=""
OVERRIDE_FILE=""
MANAGER_PATH="${AMAS_MANAGER_PATH:-/usr/local/sbin/amas-env}"
MANAGER_IMPL_PATH="${AMAS_MANAGER_IMPL_PATH:-/usr/local/libexec/amas-env-manager}"
ORIGINAL_ARGS=()

COMMAND="install"
YES=0
DRY_RUN=0
FORCE=0
SKIP_RECREATE=0
N8N_CONTAINER_ARG=""
COMPOSE_ENV_FILE_ARG=""
ANYTHINGLLM_URL_ARG=""
LLM_BASE_URL_ARG=""
WEBHOOK_URL_ARG=""
INTAKE_INTERNAL_URL_ARG=""
WORKSPACE_SLUG_ARG=""
PRIMARY_MODEL_ARG=""
CRITIC_MODEL_ARG=""
PROVIDER_NAME_ARG=""
N8N_SERVICES_ARG=""
EDITOR_TARGET="canonical"
SET_KEY=""
SET_VALUE=""

log()  { printf '[AMAS] %s\n' "$*"; }
warn() { printf '[AMAS] WARNING: %s\n' "$*" >&2; }
die()  { printf '[AMAS] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
AMAS environment installer and manager for an existing Docker Compose n8n server.

USAGE
  sudo ./scripts/amas_env_manager.sh install [options]
  sudo amas-env <command> [arguments]

INSTALL OPTIONS
  --n8n-container NAME       Select the existing primary n8n container.
  --n8n-services CSV         Override discovered n8n Compose services.
  --compose-env-file PATH    Existing stack's Compose interpolation env file.
  --anythingllm-url URL      AnythingLLM base URL reachable from n8n.
  --llm-base-url URL         OpenAI-compatible gateway base URL, normally ending /v1.
  --webhook-url URL          Public n8n webhook base URL.
  --intake-url URL           AMAS intake URL reachable from n8n.
  --workspace-slug SLUG      AnythingLLM workspace slug.
  --primary-model NAME       Primary model alias.
  --critic-model NAME        Critic model alias.
  --provider-name NAME       Provider label, for example litellm.
  --config-dir PATH          Configuration directory; default /etc/amas.
  --yes                      Accept discovered/default values and recreate services.
  --skip-recreate            Write and validate configuration without restarting n8n.
  --dry-run                  Show Compose actions without executing them.
  --force                    Update an existing AMAS installation.

MANAGEMENT COMMANDS
  status                     Show discovered deployment and redacted AMAS settings.
  paths                      Show configuration and Compose file paths.
  show                       Print AMAS settings with secrets redacted.
  edit [canonical|n8n|promptfoo]
                             Edit a file. Editing canonical regenerates derived files.
  set KEY [VALUE]            Set a canonical variable; prompts securely if VALUE omitted.
  rotate-tokens              Rotate AMAS_API_TOKEN, AMAS_INTERNAL_TOKEN and AMAS_EVAL_TOKEN.
  sync                       Regenerate n8n.env and promptfoo.env from amas.env.
  apply                      Validate the Compose override and recreate n8n services.
  verify                     Verify required variables inside every n8n execution container.
  backup                     Create a timestamped root-only configuration backup.
  uninstall                  Remove the override after recreating n8n from its original files.
  version                    Print the script version.

EXAMPLES
  sudo ./scripts/amas_env_manager.sh install --n8n-container n8n --yes
  sudo amas-env show
  sudo amas-env set LLM_PRIMARY_MODEL moderation-primary-v2
  sudo amas-env edit canonical
  sudo amas-env rotate-tokens
  sudo amas-env apply
EOF
}

refresh_paths() {
  STATE_FILE="$CONFIG_DIR/state.env"
  CANONICAL_ENV="$CONFIG_DIR/amas.env"
  N8N_ENV="$CONFIG_DIR/n8n.env"
  PROMPTFOO_ENV="$CONFIG_DIR/promptfoo.env"
  OVERRIDE_FILE="$CONFIG_DIR/docker-compose.amas.override.yml"
}
refresh_paths

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E "$SCRIPT_PATH" "$@"
    fi
    die "Run this command as root."
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

check_prerequisites() {
  need_cmd docker
  need_cmd python3
  need_cmd openssl
  docker info >/dev/null 2>&1 || die "Docker daemon is not reachable."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
}

shell_quote() {
  printf '%q' "$1"
}

write_state_var() {
  local key="$1" value="$2"
  printf '%s=' "$key"
  shell_quote "$value"
  printf '\n'
}

load_state() {
  [[ -f "$STATE_FILE" ]] || die "AMAS is not installed in $CONFIG_DIR. Run the install command first."
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  : "${COMPOSE_PROJECT:?Missing COMPOSE_PROJECT in state}"
  : "${COMPOSE_WORKDIR:?Missing COMPOSE_WORKDIR in state}"
  : "${COMPOSE_FILES:?Missing COMPOSE_FILES in state}"
  : "${N8N_SERVICES:?Missing N8N_SERVICES in state}"
  : "${PRIMARY_N8N_SERVICE:?Missing PRIMARY_N8N_SERVICE in state}"
}

is_sensitive_key() {
  [[ "$1" =~ (TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY|DATABASE_URL|DSN|AUTH|ENCRYPTION|CREDENTIAL|PRIVATE) ]]
}

random_hex() {
  openssl rand -hex "${1:-32}"
}

random_token() {
  openssl rand -hex "${1:-48}"
}

env_get() {
  local file="$1" wanted="$2" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim leading whitespace.
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -n "$line" && "$line" != \#* && "$line" == *=* ]] || continue
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" == "$wanted" ]] || continue
    value="${line#*=}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 && "$value" == \"*\" ]]; then
      value="${value:1:${#value}-2}"
      value="${value//\\\"/\"}"
      value="${value//\\\\/\\}"
    elif [[ ${#value} -ge 2 && "$value" == \'*\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    printf '%s\n' "$value"
    return 0
  done < "$file"
  return 0
}

env_set() {
  local file="$1" key="$2" value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
import os, re, sys, tempfile
from pathlib import Path
path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if "\n" in value or "\r" in value:
    raise SystemExit("Environment values cannot contain newlines")

def quote(v: str) -> str:
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'

lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out, replaced = [], False
pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
for line in lines:
    if pattern.match(line) and not line.lstrip().startswith("#"):
        if not replaced:
            out.append(f"{key}={quote(value)}")
            replaced = True
        continue
    out.append(line)
if not replaced:
    if out and out[-1] != "":
        out.append("")
    out.append(f"{key}={quote(value)}")
path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
PY
}

read_container_env() {
  local container="$1" key="$2" line
  while IFS= read -r line; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s\n' "${line#*=}"
      return 0
    fi
  done < <(docker inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)
  return 1
}

label_of() {
  local container="$1" label="$2"
  docker inspect "$container" --format "{{ index .Config.Labels \"$label\" }}" 2>/dev/null | sed '/^<no value>$/d'
}

container_image() {
  docker inspect "$1" --format '{{.Config.Image}}' 2>/dev/null
}

container_restart_policy() {
  docker inspect "$1" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null
}

container_networks() {
  docker inspect "$1" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' 2>/dev/null
}

share_network() {
  local a="$1" b="$2" n
  local -A seen=()
  while IFS= read -r n; do [[ -n "$n" ]] && seen["$n"]=1; done < <(container_networks "$a")
  while IFS= read -r n; do
    [[ -n "$n" && -n "${seen[$n]:-}" ]] && return 0
  done < <(container_networks "$b")
  return 1
}

select_from_list() {
  local prompt="$1"; shift
  local -a options=("$@")
  ((${#options[@]} > 0)) || return 1
  if ((${#options[@]} == 1)); then
    printf '%s\n' "${options[0]}"
    return 0
  fi
  if ((YES)); then
    die "$prompt Multiple candidates were found; pass --n8n-container explicitly."
  fi
  printf '%s\n' "$prompt" >&2
  local i
  for i in "${!options[@]}"; do printf '  %d) %s\n' "$((i+1))" "${options[$i]}" >&2; done
  local answer
  while true; do
    read -r -p "Selection [1-${#options[@]}]: " answer
    [[ "$answer" =~ ^[0-9]+$ ]] || continue
    ((answer >= 1 && answer <= ${#options[@]})) || continue
    printf '%s\n' "${options[$((answer-1))]}"
    return 0
  done
}

prompt_value() {
  local prompt="$1" default="$2" value
  if ((YES)); then
    printf '%s\n' "$default"
    return 0
  fi
  read -r -p "$prompt [$default]: " value
  printf '%s\n' "${value:-$default}"
}

confirm() {
  local prompt="$1"
  ((YES)) && return 0
  local answer
  read -r -p "$prompt [y/N]: " answer
  [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

backup_file() {
  local file="$1"
  [[ -e "$file" ]] || return 0
  local stamp backup_dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="$CONFIG_DIR/backups/$stamp"
  mkdir -p "$backup_dir"
  cp -a "$file" "$backup_dir/"
}

backup_all() {
  load_state
  local stamp target
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="$CONFIG_DIR/backups/amas-config-$stamp.tar.gz"
  mkdir -p "$CONFIG_DIR/backups"
  tar --exclude=./backups -C "$CONFIG_DIR" -czf "$target" .
  chmod 600 "$target"
  log "Created $target"
}

find_n8n_candidates() {
  local name image
  while IFS=$'\t' read -r name image; do
    [[ -n "$name" ]] || continue
    if [[ "${image,,}" == *n8n* ]]; then
      printf '%s\n' "$name"
    fi
  done < <(docker ps -a --format '{{.Names}}\t{{.Image}}')
}

find_related_n8n_services() {
  local project="$1" primary_container="$2" primary_image name image service restart
  primary_image="$(container_image "$primary_container")"
  local -A seen=()
  local -a services=()
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    image="$(container_image "$name")"
    service="$(label_of "$name" com.docker.compose.service)"
    restart="$(container_restart_policy "$name")"
    [[ -n "$service" ]] || continue
    if [[ "$image" == "$primary_image" ]] && { [[ "$restart" != "no" ]] || [[ "$name" == "$primary_container" ]]; }; then
      if [[ -z "${seen[$service]:-}" ]]; then
        seen["$service"]=1
        services+=("$service")
      fi
    fi
  done < <(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Names}}')
  if ((${#services[@]} == 0)); then
    services+=("$(label_of "$primary_container" com.docker.compose.service)")
  fi
  local IFS=,
  printf '%s\n' "${services[*]}"
}

find_default_compose_files() {
  local dir="$1" file
  for file in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
    [[ -f "$dir/$file" ]] && { printf '%s\n' "$dir/$file"; return 0; }
  done
  return 1
}

find_matching_container() {
  local regex="$1" primary="$2" name image
  while IFS=$'\t' read -r name image; do
    [[ -n "$name" ]] || continue
    if [[ "${name,,} ${image,,}" =~ $regex ]] && share_network "$primary" "$name"; then
      printf '%s\n' "$name"
      return 0
    fi
  done < <(docker ps --format '{{.Names}}\t{{.Image}}')
  return 1
}

container_dns_name() {
  local container="$1" service project primary_project
  service="$(label_of "$container" com.docker.compose.service)"
  project="$(label_of "$container" com.docker.compose.project)"
  primary_project="$2"
  if [[ -n "$service" && "$project" == "$primary_project" ]]; then
    printf '%s\n' "$service"
  else
    printf '%s\n' "$container"
  fi
}

normalize_base_url() {
  local value="$1"
  printf '%s\n' "${value%/}"
}

validate_url() {
  local label="$1" value="$2"
  [[ "$value" == http://* || "$value" == https://* ]] || die "$label must begin with http:// or https://: $value"
  [[ "$value" != *[[:space:]]* && "$value" != *'"'* && "$value" != *'\'* ]] || \
    die "$label contains whitespace, quotes, or backslashes: $value"
  [[ "${value,,}" != *example.* ]] || die "$label still contains an example placeholder: $value"
}

validate_simple_value() {
  local label="$1" value="$2"
  [[ -n "$value" ]] || die "$label cannot be empty."
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *'"'* && "$value" != *'\\'* ]] || \
    die "$label contains unsupported characters."
}

value_from_env_dump() {
  local dump="$1" wanted="$2" line
  while IFS= read -r line; do
    [[ "$line" == "$wanted="* ]] && { printf '%s\n' "${line#*=}"; return 0; }
  done <<< "$dump"
  return 1
}

write_canonical_env() {
  local file="$1"

  local api_token internal_token eval_token workflow_version corpus_version max_file_bytes
  api_token="$(env_get "$file" AMAS_API_TOKEN)"; api_token="${api_token:-$(random_token 48)}"
  internal_token="$(env_get "$file" AMAS_INTERNAL_TOKEN)"; internal_token="${internal_token:-$(random_token 48)}"
  eval_token="$(env_get "$file" AMAS_EVAL_TOKEN)"; eval_token="${eval_token:-$(random_token 48)}"
  workflow_version="$(env_get "$file" AMAS_WORKFLOW_VERSION)"; workflow_version="${workflow_version:-amas-1.0.0}"
  corpus_version="$(env_get "$file" AMAS_CORPUS_VERSION)"; corpus_version="${corpus_version:-policy-corpus-2026.06.1}"
  max_file_bytes="$(env_get "$file" AMAS_MAX_FILE_BYTES)"; max_file_bytes="${max_file_bytes:-26214400}"

  local anythingllm_api_key llm_api_key
  anythingllm_api_key="$(env_get "$file" ANYTHINGLLM_API_KEY)"
  llm_api_key="$(env_get "$file" LLM_API_KEY)"

  local postgres_db postgres_user pg_owner pg_app pg_readonly database_url
  postgres_db="$(env_get "$file" POSTGRES_DB)"; postgres_db="${postgres_db:-amas}"
  postgres_user="$(env_get "$file" POSTGRES_USER)"; postgres_user="${postgres_user:-amas_owner}"
  pg_owner="$(env_get "$file" POSTGRES_PASSWORD)"; pg_owner="${pg_owner:-$(random_hex 32)}"
  pg_app="$(env_get "$file" AMAS_APP_PASSWORD)"; pg_app="${pg_app:-$(random_hex 32)}"
  pg_readonly="$(env_get "$file" AMAS_READONLY_PASSWORD)"; pg_readonly="${pg_readonly:-$(random_hex 32)}"
  database_url="$(env_get "$file" AMAS_DATABASE_URL)"
  database_url="${database_url:-postgresql://amas_app:$pg_app@amas-postgres:5432/$postgres_db}"

  local garage_rpc garage_admin garage_metrics s3_endpoint s3_public_endpoint s3_region s3_bucket s3_access s3_secret
  garage_rpc="$(env_get "$file" GARAGE_RPC_SECRET)"; garage_rpc="${garage_rpc:-$(random_hex 32)}"
  garage_admin="$(env_get "$file" GARAGE_ADMIN_TOKEN)"; garage_admin="${garage_admin:-$(random_token 40)}"
  garage_metrics="$(env_get "$file" GARAGE_METRICS_TOKEN)"; garage_metrics="${garage_metrics:-$(random_token 40)}"
  s3_endpoint="$(env_get "$file" S3_ENDPOINT)"; s3_endpoint="${s3_endpoint:-http://amas-garage:3900}"
  s3_public_endpoint="$(env_get "$file" S3_PUBLIC_ENDPOINT)"; s3_public_endpoint="${s3_public_endpoint:-http://127.0.0.1:3900}"
  s3_region="$(env_get "$file" S3_REGION)"; s3_region="${s3_region:-garage}"
  s3_bucket="$(env_get "$file" S3_BUCKET)"; s3_bucket="${s3_bucket:-amas}"
  s3_access="$(env_get "$file" S3_ACCESS_KEY)"; s3_access="${s3_access:-GK$(random_hex 16)}"
  s3_secret="$(env_get "$file" S3_SECRET_KEY)"; s3_secret="${s3_secret:-$(random_hex 32)}"

  local disable_sharing disable_telemetry
  disable_sharing="$(env_get "$file" PROMPTFOO_DISABLE_SHARING)"; disable_sharing="${disable_sharing:-1}"
  disable_telemetry="$(env_get "$file" PROMPTFOO_DISABLE_TELEMETRY)"; disable_telemetry="${disable_telemetry:-1}"

  local tmp
  tmp="$(mktemp "$CONFIG_DIR/.amas.env.XXXXXX")"
  cat > "$tmp" <<EOF
# AMAS canonical server configuration.
# Generated by amas-env $VERSION on $(date -u +%Y-%m-%dT%H:%M:%SZ).
# Mode 0600. Do not commit or paste this file into support channels.

# AMAS authentication and provenance
AMAS_API_TOKEN="$api_token"
AMAS_INTERNAL_TOKEN="$internal_token"
AMAS_EVAL_TOKEN="$eval_token"
AMAS_WORKFLOW_VERSION="$workflow_version"
AMAS_CORPUS_VERSION="$corpus_version"
AMAS_MAX_FILE_BYTES="$max_file_bytes"

# Existing n8n and AMAS service routing
N8N_INTERNAL_BASE_URL="$N8N_INTERNAL_BASE_URL_VALUE"
AMAS_INTAKE_INTERNAL_URL="$AMAS_INTAKE_INTERNAL_URL_VALUE"
AMAS_EVAL_WEBHOOK_URL="$AMAS_EVAL_WEBHOOK_URL_VALUE"

# AnythingLLM knowledge service
ANYTHINGLLM_BASE_URL="$ANYTHINGLLM_BASE_URL_VALUE"
ANYTHINGLLM_WORKSPACE_SLUG="$ANYTHINGLLM_WORKSPACE_SLUG_VALUE"
# Prefer the named n8n credential; this root-only value is retained for CLI ingestion tools.
ANYTHINGLLM_API_KEY="$anythingllm_api_key"

# OpenAI-compatible model gateway
LLM_BASE_URL="$LLM_BASE_URL_VALUE"
LLM_PRIMARY_MODEL="$LLM_PRIMARY_MODEL_VALUE"
LLM_CRITIC_MODEL="$LLM_CRITIC_MODEL_VALUE"
LLM_PROVIDER_NAME="$LLM_PROVIDER_NAME_VALUE"
# Prefer the named n8n credential; this root-only value is retained for CLI tools.
LLM_API_KEY="$llm_api_key"

# Dedicated AMAS PostgreSQL values for the optional AMAS support stack
POSTGRES_DB="$postgres_db"
POSTGRES_USER="$postgres_user"
POSTGRES_PASSWORD="$pg_owner"
AMAS_APP_PASSWORD="$pg_app"
AMAS_READONLY_PASSWORD="$pg_readonly"
AMAS_DATABASE_URL="$database_url"

# S3-compatible object storage values for the optional AMAS support stack
GARAGE_RPC_SECRET="$garage_rpc"
GARAGE_ADMIN_TOKEN="$garage_admin"
GARAGE_METRICS_TOKEN="$garage_metrics"
S3_ENDPOINT="$s3_endpoint"
S3_PUBLIC_ENDPOINT="$s3_public_endpoint"
S3_REGION="$s3_region"
S3_BUCKET="$s3_bucket"
S3_ACCESS_KEY="$s3_access"
S3_SECRET_KEY="$s3_secret"

# Promptfoo privacy controls
PROMPTFOO_DISABLE_SHARING="$disable_sharing"
PROMPTFOO_DISABLE_TELEMETRY="$disable_telemetry"
EOF
  chmod 600 "$tmp"
  mv "$tmp" "$file"
}

sync_derived_envs() {
  [[ -f "$CANONICAL_ENV" ]] || die "Missing $CANONICAL_ENV"
  local required=(
    AMAS_API_TOKEN AMAS_INTERNAL_TOKEN AMAS_EVAL_TOKEN AMAS_WORKFLOW_VERSION AMAS_CORPUS_VERSION
    N8N_INTERNAL_BASE_URL AMAS_INTAKE_INTERNAL_URL ANYTHINGLLM_BASE_URL
    ANYTHINGLLM_WORKSPACE_SLUG LLM_BASE_URL LLM_PRIMARY_MODEL LLM_CRITIC_MODEL LLM_PROVIDER_NAME
    AMAS_EVAL_WEBHOOK_URL
  )
  local key value
  for key in "${required[@]}"; do
    value="$(env_get "$CANONICAL_ENV" "$key" || true)"
    [[ -n "$value" ]] || die "Required value $key is empty in $CANONICAL_ENV"
  done

  local tmp
  tmp="$(mktemp "$CONFIG_DIR/.n8n.env.XXXXXX")"
  cat > "$tmp" <<EOF
# AMAS variables injected into the existing n8n execution services.
# Generated from $CANONICAL_ENV. Edit the canonical file, then run: amas-env sync
N8N_BLOCK_ENV_ACCESS_IN_NODE="false"
AMAS_API_TOKEN="$(env_get "$CANONICAL_ENV" AMAS_API_TOKEN)"
AMAS_INTERNAL_TOKEN="$(env_get "$CANONICAL_ENV" AMAS_INTERNAL_TOKEN)"
AMAS_EVAL_TOKEN="$(env_get "$CANONICAL_ENV" AMAS_EVAL_TOKEN)"
AMAS_WORKFLOW_VERSION="$(env_get "$CANONICAL_ENV" AMAS_WORKFLOW_VERSION)"
AMAS_CORPUS_VERSION="$(env_get "$CANONICAL_ENV" AMAS_CORPUS_VERSION)"
N8N_INTERNAL_BASE_URL="$(env_get "$CANONICAL_ENV" N8N_INTERNAL_BASE_URL)"
AMAS_INTAKE_INTERNAL_URL="$(env_get "$CANONICAL_ENV" AMAS_INTAKE_INTERNAL_URL)"
ANYTHINGLLM_BASE_URL="$(env_get "$CANONICAL_ENV" ANYTHINGLLM_BASE_URL)"
ANYTHINGLLM_WORKSPACE_SLUG="$(env_get "$CANONICAL_ENV" ANYTHINGLLM_WORKSPACE_SLUG)"
LLM_BASE_URL="$(env_get "$CANONICAL_ENV" LLM_BASE_URL)"
LLM_PRIMARY_MODEL="$(env_get "$CANONICAL_ENV" LLM_PRIMARY_MODEL)"
LLM_CRITIC_MODEL="$(env_get "$CANONICAL_ENV" LLM_CRITIC_MODEL)"
LLM_PROVIDER_NAME="$(env_get "$CANONICAL_ENV" LLM_PROVIDER_NAME)"
EOF
  chmod 600 "$tmp"
  mv "$tmp" "$N8N_ENV"

  tmp="$(mktemp "$CONFIG_DIR/.promptfoo.env.XXXXXX")"
  cat > "$tmp" <<EOF
# AMAS Promptfoo environment.
AMAS_EVAL_WEBHOOK_URL="$(env_get "$CANONICAL_ENV" AMAS_EVAL_WEBHOOK_URL)"
AMAS_EVAL_TOKEN="$(env_get "$CANONICAL_ENV" AMAS_EVAL_TOKEN)"
PROMPTFOO_DISABLE_SHARING="$(env_get "$CANONICAL_ENV" PROMPTFOO_DISABLE_SHARING || printf 1)"
PROMPTFOO_DISABLE_TELEMETRY="$(env_get "$CANONICAL_ENV" PROMPTFOO_DISABLE_TELEMETRY || printf 1)"
EOF
  chmod 600 "$tmp"
  mv "$tmp" "$PROMPTFOO_ENV"
  log "Regenerated $N8N_ENV and $PROMPTFOO_ENV"
}

write_override() {
  local services_csv="$1" tmp service
  tmp="$(mktemp "$CONFIG_DIR/.compose.override.XXXXXX")"
  printf 'services:\n' > "$tmp"
  IFS=',' read -r -a _services <<< "$services_csv"
  for service in "${_services[@]}"; do
    [[ "$service" =~ ^[A-Za-z0-9._-]+$ ]] || die "Unsafe Compose service name: $service"
    cat >> "$tmp" <<EOF
  $service:
    env_file:
      - $N8N_ENV
    environment:
      N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"
EOF
  done
  chmod 600 "$tmp"
  mv "$tmp" "$OVERRIDE_FILE"
  log "Created reversible Compose override: $OVERRIDE_FILE"
}

build_compose_cmd() {
  local mode="${1:-with_override}" file
  COMPOSE_CMD=(docker compose -p "$COMPOSE_PROJECT")
  if [[ -n "${COMPOSE_ENV_FILE:-}" ]]; then
    COMPOSE_CMD+=(--env-file "$COMPOSE_ENV_FILE")
  fi
  IFS=',' read -r -a _compose_files <<< "$COMPOSE_FILES"
  for file in "${_compose_files[@]}"; do COMPOSE_CMD+=(-f "$file"); done
  if [[ "$mode" == "with_override" ]]; then
    COMPOSE_CMD+=(-f "$OVERRIDE_FILE")
  fi
}

print_command() {
  printf '[AMAS] DRY-RUN:'
  printf ' %q' "$@"
  printf '\n'
}

compose_exec() {
  local mode="$1"; shift
  build_compose_cmd "$mode"
  if ((DRY_RUN)); then
    (cd "$COMPOSE_WORKDIR" && print_command "${COMPOSE_CMD[@]}" "$@")
  else
    (cd "$COMPOSE_WORKDIR" && "${COMPOSE_CMD[@]}" "$@")
  fi
}

validate_compose() {
  [[ -f "$OVERRIDE_FILE" ]] || die "Missing $OVERRIDE_FILE"
  log "Validating merged Docker Compose configuration"
  compose_exec with_override config --quiet
}

apply_override() {
  load_state
  validate_compose
  local -a services
  IFS=',' read -r -a services <<< "$N8N_SERVICES"
  log "Recreating only these n8n services: $N8N_SERVICES"
  compose_exec with_override up -d --no-deps --force-recreate "${services[@]}"
  ((DRY_RUN)) || verify_installation
}

containers_for_services() {
  local service container
  IFS=',' read -r -a _services <<< "$N8N_SERVICES"
  for service in "${_services[@]}"; do
    container="$(docker ps -a \
      --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
      --filter "label=com.docker.compose.service=$service" \
      --format '{{.Names}}' | head -n1)"
    [[ -n "$container" ]] && printf '%s\n' "$container"
  done
}

verify_installation() {
  load_state
  local required=(
    N8N_BLOCK_ENV_ACCESS_IN_NODE AMAS_API_TOKEN AMAS_INTERNAL_TOKEN AMAS_EVAL_TOKEN
    AMAS_WORKFLOW_VERSION AMAS_CORPUS_VERSION N8N_INTERNAL_BASE_URL AMAS_INTAKE_INTERNAL_URL
    ANYTHINGLLM_BASE_URL ANYTHINGLLM_WORKSPACE_SLUG LLM_BASE_URL LLM_PRIMARY_MODEL
    LLM_CRITIC_MODEL LLM_PROVIDER_NAME
  )
  local container key value dump failures=0 found=0
  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    found=1
    log "Checking $container"
    dump="$(docker inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)"
    for key in "${required[@]}"; do
      value="$(value_from_env_dump "$dump" "$key" || true)"
      if [[ -z "$value" ]]; then
        printf '  %-38s %s\n' "$key" "MISSING"
        failures=$((failures+1))
      elif [[ "$key" == "N8N_BLOCK_ENV_ACCESS_IN_NODE" && "$value" != "false" ]]; then
        printf '  %-38s %s\n' "$key" "INVALID ($value)"
        failures=$((failures+1))
      else
        printf '  %-38s %s\n' "$key" "set"
      fi
    done
  done < <(containers_for_services)
  ((found)) || die "No n8n containers found for the stored Compose services."
  if ((failures)); then
    die "$failures required n8n environment checks failed."
  fi
  log "AMAS variables are present in all discovered n8n execution containers."
}

show_redacted_env() {
  local file="${1:-$CANONICAL_ENV}" line key value
  [[ -f "$file" ]] || die "Missing $file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "${line//[[:space:]]/}" ]]; then
      printf '%s\n' "$line"
      continue
    fi
    if [[ "$line" == *=* ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      if is_sensitive_key "$key"; then
        printf '%s="<redacted>"\n' "$key"
      else
        printf '%s=%s\n' "$key" "$value"
      fi
    else
      printf '%s\n' "$line"
    fi
  done < "$file"
}

show_paths() {
  load_state
  cat <<EOF
Configuration directory:  $CONFIG_DIR
Canonical environment:    $CANONICAL_ENV
n8n environment subset:   $N8N_ENV
Promptfoo environment:    $PROMPTFOO_ENV
Compose override:         $OVERRIDE_FILE
State file:               $STATE_FILE
Existing Compose project: $COMPOSE_PROJECT
Compose working directory:$COMPOSE_WORKDIR
Compose files:            $COMPOSE_FILES
Compose interpolation env:${COMPOSE_ENV_FILE:-<default/none>}
n8n services:             $N8N_SERVICES
Manager command:          $MANAGER_PATH
AMAS project root:        ${AMAS_PROJECT_ROOT:-<unknown>}
EOF
}

show_status() {
  load_state
  show_paths
  printf '\nContainers:\n'
  local container
  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    docker ps -a --filter "name=^/${container}$" \
      --format '  {{.Names}}\t{{.Image}}\t{{.Status}}'
  done < <(containers_for_services)
  printf '\nRedacted canonical settings:\n'
  show_redacted_env "$CANONICAL_ENV"
}

install_manager_command() {
  install -d -m 0755 "$(dirname "$MANAGER_IMPL_PATH")" "$(dirname "$MANAGER_PATH")"
  install -m 0750 "$SCRIPT_PATH" "$MANAGER_IMPL_PATH"
  local tmp
  tmp="$(mktemp "$(dirname "$MANAGER_PATH")/.amas-env.XXXXXX")"
  cat > "$tmp" <<EOF
#!/usr/bin/env bash
export AMAS_CONFIG_DIR=$(shell_quote "$CONFIG_DIR")
export AMAS_MANAGER_PATH=$(shell_quote "$MANAGER_PATH")
export AMAS_MANAGER_IMPL_PATH=$(shell_quote "$MANAGER_IMPL_PATH")
exec $(shell_quote "$MANAGER_IMPL_PATH") "\$@"
EOF
  chmod 0750 "$tmp"
  mv "$tmp" "$MANAGER_PATH"
  log "Installed management command: $MANAGER_PATH"
}

install_command() {
  check_prerequisites
  mkdir -p "$CONFIG_DIR/backups"
  chmod 700 "$CONFIG_DIR" "$CONFIG_DIR/backups"

  if [[ -f "$STATE_FILE" ]] && (( ! FORCE )); then
    die "An AMAS installation already exists at $CONFIG_DIR. Use --force to update it."
  fi

  local primary_container project workdir config_files primary_service services compose_env
  local -a candidates
  if [[ -n "$N8N_CONTAINER_ARG" ]]; then
    docker inspect "$N8N_CONTAINER_ARG" >/dev/null 2>&1 || die "n8n container not found: $N8N_CONTAINER_ARG"
    primary_container="$N8N_CONTAINER_ARG"
  else
    mapfile -t candidates < <(find_n8n_candidates)
    ((${#candidates[@]})) || die "No n8n container was discovered. Pass --n8n-container NAME."
    primary_container="$(select_from_list "Select the primary n8n container:" "${candidates[@]}")"
  fi

  project="$(label_of "$primary_container" com.docker.compose.project)"
  workdir="$(label_of "$primary_container" com.docker.compose.project.working_dir)"
  config_files="$(label_of "$primary_container" com.docker.compose.project.config_files)"
  primary_service="$(label_of "$primary_container" com.docker.compose.service)"

  [[ -n "$project" && -n "$workdir" && -n "$primary_service" ]] || \
    die "$primary_container is not managed by Docker Compose or lacks required Compose labels."
  if [[ -z "$config_files" ]]; then
    config_files="$(find_default_compose_files "$workdir" || true)"
  fi
  [[ -n "$config_files" ]] || die "Could not determine the existing Compose file."
  config_files="${config_files//, /,}"
  local f
  IFS=',' read -r -a _files <<< "$config_files"
  for f in "${_files[@]}"; do [[ -f "$f" ]] || die "Compose file does not exist: $f"; done

  services="${N8N_SERVICES_ARG:-$(find_related_n8n_services "$project" "$primary_container")}"
  [[ -n "$services" ]] || die "No persistent n8n Compose service was discovered."

  compose_env="$COMPOSE_ENV_FILE_ARG"
  if [[ -z "$compose_env" && -f "$workdir/.env" ]]; then compose_env="$workdir/.env"; fi
  if [[ -n "$compose_env" && ! -f "$compose_env" ]]; then die "Compose env file does not exist: $compose_env"; fi

  local existing_webhook anythingllm_url llm_url anythingllm_container llm_container host
  existing_webhook="${WEBHOOK_URL_ARG:-$(read_container_env "$primary_container" WEBHOOK_URL || true)}"
  [[ -n "$existing_webhook" ]] || existing_webhook="$(read_container_env "$primary_container" N8N_EDITOR_BASE_URL || true)"
  [[ -n "$existing_webhook" ]] || existing_webhook="https://automation.example.edu/"
  existing_webhook="$(prompt_value "Public n8n webhook base URL" "$existing_webhook")"
  existing_webhook="$(normalize_base_url "$existing_webhook")"

  anythingllm_url="$ANYTHINGLLM_URL_ARG"
  [[ -n "$anythingllm_url" ]] || anythingllm_url="$(read_container_env "$primary_container" ANYTHINGLLM_BASE_URL || true)"
  if [[ -z "$anythingllm_url" ]]; then
    anythingllm_container="$(find_matching_container 'anything[-_]?llm' "$primary_container" || true)"
    if [[ -n "$anythingllm_container" ]]; then
      host="$(container_dns_name "$anythingllm_container" "$project")"
      anythingllm_url="http://$host:3001"
    fi
  fi
  anythingllm_url="$(prompt_value "AnythingLLM URL reachable from n8n" "${anythingllm_url:-http://anythingllm:3001}")"

  llm_url="$LLM_BASE_URL_ARG"
  [[ -n "$llm_url" ]] || llm_url="$(read_container_env "$primary_container" LLM_BASE_URL || true)"
  if [[ -z "$llm_url" ]]; then
    llm_container="$(find_matching_container 'litellm|llm[-_]?gateway' "$primary_container" || true)"
    if [[ -n "$llm_container" ]]; then
      host="$(container_dns_name "$llm_container" "$project")"
      llm_url="http://$host:4000/v1"
    fi
  fi
  llm_url="$(prompt_value "OpenAI-compatible model gateway URL" "${llm_url:-http://litellm:4000/v1}")"

  validate_url "Public n8n webhook base URL" "$existing_webhook"
  validate_url "AnythingLLM URL" "$anythingllm_url"
  validate_url "Model gateway URL" "$llm_url"
  validate_url "AMAS intake URL" "${INTAKE_INTERNAL_URL_ARG:-http://amas-intake-api:8080}"
  validate_simple_value "AnythingLLM workspace slug" "${WORKSPACE_SLUG_ARG:-assessment-moderation-authoritative}"
  validate_simple_value "Primary model alias" "${PRIMARY_MODEL_ARG:-moderation-primary}"
  validate_simple_value "Critic model alias" "${CRITIC_MODEL_ARG:-moderation-critic}"
  validate_simple_value "Provider name" "${PROVIDER_NAME_ARG:-litellm}"
  [[ "${llm_url%/}" == */v1 ]] || warn "The model gateway URL does not end in /v1; confirm that it exposes /chat/completions at the configured base."

  N8N_INTERNAL_BASE_URL_VALUE="http://$primary_service:5678"
  AMAS_INTAKE_INTERNAL_URL_VALUE="${INTAKE_INTERNAL_URL_ARG:-http://amas-intake-api:8080}"
  AMAS_EVAL_WEBHOOK_URL_VALUE="${existing_webhook%/}/webhook/amas/eval/moderate"
  ANYTHINGLLM_BASE_URL_VALUE="$(normalize_base_url "$anythingllm_url")"
  ANYTHINGLLM_WORKSPACE_SLUG_VALUE="${WORKSPACE_SLUG_ARG:-assessment-moderation-authoritative}"
  LLM_BASE_URL_VALUE="$(normalize_base_url "$llm_url")"
  LLM_PRIMARY_MODEL_VALUE="${PRIMARY_MODEL_ARG:-moderation-primary}"
  LLM_CRITIC_MODEL_VALUE="${CRITIC_MODEL_ARG:-moderation-critic}"
  LLM_PROVIDER_NAME_VALUE="${PROVIDER_NAME_ARG:-litellm}"

  if [[ -f "$STATE_FILE" ]]; then
    backup_file "$STATE_FILE"; backup_file "$CANONICAL_ENV"; backup_file "$N8N_ENV"
    backup_file "$PROMPTFOO_ENV"; backup_file "$OVERRIDE_FILE"
  fi

  # Rebuild the canonical file using current routing while preserving generated secrets.
  write_canonical_env "$CANONICAL_ENV"
  chmod 600 "$CANONICAL_ENV"
  sync_derived_envs
  write_override "$services"

  {
    write_state_var AMAS_ENV_MANAGER_VERSION "$VERSION"
    write_state_var AMAS_PROJECT_ROOT "$SOURCE_PROJECT_ROOT"
    write_state_var COMPOSE_PROJECT "$project"
    write_state_var COMPOSE_WORKDIR "$workdir"
    write_state_var COMPOSE_FILES "$config_files"
    write_state_var COMPOSE_ENV_FILE "$compose_env"
    write_state_var PRIMARY_N8N_CONTAINER "$primary_container"
    write_state_var PRIMARY_N8N_SERVICE "$primary_service"
    write_state_var N8N_SERVICES "$services"
    write_state_var INSTALLED_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$STATE_FILE"
  chmod 600 "$STATE_FILE"
  install_manager_command

  # Load the state just written so Compose helper functions can operate.
  load_state
  validate_compose

  cat <<EOF

AMAS configuration is ready.
  Existing Compose project: $project
  n8n services:             $services
  Canonical environment:    $CANONICAL_ENV
  Compose override:         $OVERRIDE_FILE
  Promptfoo environment:    $PROMPTFOO_ENV
EOF

  if ((SKIP_RECREATE)); then
    log "Skipped n8n recreation. Apply later with: $MANAGER_PATH apply"
  elif ((YES)) || confirm "Recreate only the listed n8n services with the AMAS override now?"; then
    apply_override
  else
    log "No service was restarted. Apply later with: $MANAGER_PATH apply"
  fi

  cat <<'EOF'

Manual security-bound steps still required in n8n:
  1. Create/bind the credential named "AMAS PostgreSQL".
  2. Create/bind "AMAS AnythingLLM API" using HTTP Header Auth.
  3. Create/bind "AMAS LLM API" using HTTP Header Auth.
  4. Import the AMAS workflows as drafts, inspect them, then publish deliberately.

Useful commands:
  sudo amas-env show
  sudo amas-env verify
  sudo amas-env edit canonical
EOF
}

edit_command() {
  load_state
  local target="${1:-canonical}" file editor
  case "$target" in
    canonical) file="$CANONICAL_ENV" ;;
    n8n) file="$N8N_ENV"; warn "This is generated from amas.env; direct edits will be overwritten by sync." ;;
    promptfoo) file="$PROMPTFOO_ENV"; warn "This is generated from amas.env; direct edits will be overwritten by sync." ;;
    *) die "Unknown edit target: $target" ;;
  esac
  editor="${EDITOR:-nano}"
  command -v "${editor%% *}" >/dev/null 2>&1 || editor="vi"
  backup_file "$file"
  # Intentionally permit EDITOR arguments such as "vim -f".
  # shellcheck disable=SC2086
  $editor "$file"
  chmod 600 "$file"
  if [[ "$target" == "canonical" ]]; then
    sync_derived_envs
    log "Changes are staged. Run: $MANAGER_PATH apply"
  fi
}

set_command() {
  load_state
  local key="${1:-}" value="${2-}"
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "KEY must contain only uppercase letters, numbers and underscores."
  if [[ $# -lt 2 ]]; then
    if is_sensitive_key "$key"; then
      read -r -s -p "Value for $key: " value; printf '\n'
    else
      read -r -p "Value for $key: " value
    fi
  fi
  backup_file "$CANONICAL_ENV"
  env_set "$CANONICAL_ENV" "$key" "$value"
  sync_derived_envs
  log "$key updated. Apply it with: $MANAGER_PATH apply"
}

rotate_tokens_command() {
  load_state
  backup_file "$CANONICAL_ENV"
  env_set "$CANONICAL_ENV" AMAS_API_TOKEN "$(random_token 48)"
  env_set "$CANONICAL_ENV" AMAS_INTERNAL_TOKEN "$(random_token 48)"
  env_set "$CANONICAL_ENV" AMAS_EVAL_TOKEN "$(random_token 48)"
  sync_derived_envs
  warn "Clients using the old API/evaluation tokens must be updated after the n8n services are recreated."
  if ((YES)) || confirm "Apply the rotated tokens to n8n now?"; then apply_override; fi
}

uninstall_command() {
  load_state
  warn "This will recreate n8n without the AMAS Compose override. It will not delete AMAS data or workflows."
  if ! ((YES)) && ! confirm "Continue?"; then
    log "Cancelled."
    return 0
  fi
  local -a services
  IFS=',' read -r -a services <<< "$N8N_SERVICES"
  log "Recreating n8n from the original Compose files"
  compose_exec without_override up -d --no-deps --force-recreate "${services[@]}"
  local stamp removed
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  removed="${CONFIG_DIR}.removed.$stamp"
  if ((DRY_RUN)); then
    log "DRY-RUN: would move $CONFIG_DIR to $removed and remove $MANAGER_PATH"
  else
    mv "$CONFIG_DIR" "$removed"
    rm -f "$MANAGER_PATH" "$MANAGER_IMPL_PATH"
    log "AMAS environment integration removed. Configuration retained at $removed"
  fi
}

parse_args() {
  if (($#)); then
    case "$1" in
      install|status|paths|show|edit|set|rotate-tokens|sync|apply|verify|backup|uninstall|version|help|-h|--help)
        COMMAND="$1"; shift ;;
    esac
  fi
  while (($#)); do
    case "$1" in
      --n8n-container) N8N_CONTAINER_ARG="${2:?}"; shift 2 ;;
      --n8n-services) N8N_SERVICES_ARG="${2:?}"; shift 2 ;;
      --compose-env-file) COMPOSE_ENV_FILE_ARG="${2:?}"; shift 2 ;;
      --anythingllm-url) ANYTHINGLLM_URL_ARG="${2:?}"; shift 2 ;;
      --llm-base-url) LLM_BASE_URL_ARG="${2:?}"; shift 2 ;;
      --webhook-url) WEBHOOK_URL_ARG="${2:?}"; shift 2 ;;
      --intake-url) INTAKE_INTERNAL_URL_ARG="${2:?}"; shift 2 ;;
      --workspace-slug) WORKSPACE_SLUG_ARG="${2:?}"; shift 2 ;;
      --primary-model) PRIMARY_MODEL_ARG="${2:?}"; shift 2 ;;
      --critic-model) CRITIC_MODEL_ARG="${2:?}"; shift 2 ;;
      --provider-name) PROVIDER_NAME_ARG="${2:?}"; shift 2 ;;
      --config-dir) CONFIG_DIR="${2:?}"; refresh_paths; shift 2 ;;
      --yes|-y) YES=1; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      --force) FORCE=1; shift ;;
      --skip-recreate) SKIP_RECREATE=1; shift ;;
      --) shift; break ;;
      *)
        case "$COMMAND" in
          edit) EDITOR_TARGET="$1"; shift ;;
          set)
            [[ -z "$SET_KEY" ]] && { SET_KEY="$1"; shift; continue; }
            [[ -z "$SET_VALUE" ]] && { SET_VALUE="$1"; shift; continue; }
            die "Too many arguments for set"
            ;;
          *) die "Unknown argument: $1" ;;
        esac
        ;;
    esac
  done
}

main() {
  ORIGINAL_ARGS=("$@")
  parse_args "$@"
  case "$COMMAND" in
    help|-h|--help) usage ;;
    version) printf 'amas-env %s\n' "$VERSION" ;;
    install)
      require_root "${ORIGINAL_ARGS[@]}"
      install_command
      ;;
    *)
      require_root "${ORIGINAL_ARGS[@]}"
      check_prerequisites
      case "$COMMAND" in
        status) show_status ;;
        paths) show_paths ;;
        show) load_state; show_redacted_env "$CANONICAL_ENV" ;;
        edit) edit_command "$EDITOR_TARGET" ;;
        set)
          [[ -n "$SET_KEY" ]] || die "Usage: amas-env set KEY [VALUE]"
          if [[ -n "$SET_VALUE" ]]; then set_command "$SET_KEY" "$SET_VALUE"; else set_command "$SET_KEY"; fi
          ;;
        rotate-tokens) rotate_tokens_command ;;
        sync) load_state; sync_derived_envs ;;
        apply) apply_override ;;
        verify) verify_installation ;;
        backup) backup_all ;;
        uninstall) uninstall_command ;;
        *) usage; exit 2 ;;
      esac
      ;;
  esac
}

main "$@"
