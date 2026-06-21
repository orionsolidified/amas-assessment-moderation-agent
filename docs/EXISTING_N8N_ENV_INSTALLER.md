# Existing n8n server: automated AMAS environment integration

Use `scripts/amas_env_manager.sh` when n8n, AnythingLLM, and Promptfoo already run on the server. The script integrates AMAS without starting a second n8n instance and without overwriting the existing n8n encryption key, database settings, public routing, or user-management secrets.

## What the installer automates

The installer:

1. discovers the existing Docker Compose-managed n8n container;
2. reads its Compose project labels, working directory, Compose files, services, and default `.env` location;
3. detects persistent n8n execution services such as the main instance, workers, and webhook processors that use the same image;
4. derives or prompts for the n8n webhook, AnythingLLM, model-gateway, and AMAS intake URLs;
5. creates root-only configuration under `/etc/amas`;
6. generates independent AMAS API, internal, and evaluation tokens;
7. creates a minimal `n8n.env` containing only variables required by AMAS workflows;
8. creates a separate `promptfoo.env`;
9. creates a reversible Compose override rather than editing the original Compose file;
10. validates the merged Compose configuration;
11. recreates only the selected n8n services; and
12. verifies required variables inside every selected n8n container.

It also installs the management command:

```text
/usr/local/sbin/amas-env
```

## What it deliberately does not automate

The script does not:

- replace or rotate the existing `N8N_ENCRYPTION_KEY`;
- modify the existing n8n database configuration;
- put AnythingLLM or model-gateway API keys into container environment variables;
- create encrypted n8n credentials without an explicit administrator action;
- publish imported workflows;
- start a second n8n instance;
- start the optional AMAS PostgreSQL, object-storage, or intake-API services.

Those boundaries prevent accidental credential loss, unintended publication, and disruption of the existing automation platform.

## Prerequisites

- Linux server with Bash;
- root or `sudo` access;
- Docker Engine;
- Docker Compose v2;
- Python 3;
- OpenSSL;
- an existing n8n container managed by Docker Compose.

The script refuses to modify a plain `docker run` deployment because it needs a reproducible Compose definition for safe recreation and rollback.

## Recommended interactive installation

From the AMAS project directory:

```bash
cd /opt/amas-assessment-moderation-agent
chmod +x scripts/amas_env_manager.sh
sudo ./scripts/amas_env_manager.sh install
```

The script lists n8n containers when more than one candidate exists. Confirm the detected URLs carefully. Internal URLs must be reachable **from the n8n containers**, not merely from the host shell.

To create and validate the files without restarting n8n:

```bash
sudo ./scripts/amas_env_manager.sh install --skip-recreate
sudo amas-env show
sudo amas-env apply
```

## Non-interactive example

Replace the values with the server's actual service names and domains:

```bash
sudo ./scripts/amas_env_manager.sh install \
  --n8n-container n8n \
  --webhook-url https://automation.orionsolidified.io \
  --anythingllm-url http://anythingllm:3001 \
  --llm-base-url http://litellm:4000/v1 \
  --intake-url http://amas-intake-api:8080 \
  --workspace-slug assessment-moderation-authoritative \
  --primary-model moderation-primary \
  --critic-model moderation-critic \
  --provider-name litellm \
  --yes
```

When discovery finds multiple persistent n8n services, the override is applied to each. Override the list when necessary:

```bash
sudo ./scripts/amas_env_manager.sh install \
  --n8n-container n8n-main \
  --n8n-services n8n,n8n-worker,n8n-webhook \
  --webhook-url https://automation.orionsolidified.io \
  --anythingllm-url http://anythingllm:3001 \
  --llm-base-url http://litellm:4000/v1 \
  --yes
```

If the existing stack was launched with a non-default Compose interpolation file, specify it explicitly:

```bash
sudo ./scripts/amas_env_manager.sh install \
  --n8n-container n8n \
  --compose-env-file /opt/automation/production.env \
  --webhook-url https://automation.orionsolidified.io \
  --anythingllm-url http://anythingllm:3001 \
  --llm-base-url http://litellm:4000/v1
```

## Files created

| Path | Purpose | Mode |
|---|---|---:|
| `/etc/amas/amas.env` | Canonical AMAS server configuration | `0600` |
| `/etc/amas/n8n.env` | Minimal AMAS subset injected into n8n | `0600` |
| `/etc/amas/promptfoo.env` | Promptfoo endpoint, token, and privacy settings | `0600` |
| `/etc/amas/docker-compose.amas.override.yml` | Reversible n8n Compose override | `0600` |
| `/etc/amas/state.env` | Discovered Compose project metadata | `0600` |
| `/etc/amas/backups/` | Timestamped backups | root only |
| `/usr/local/sbin/amas-env` | Management command | `0750` |

Run all management commands with `sudo` because the files contain secrets.

## Management commands

Show configuration with secrets redacted:

```bash
sudo amas-env show
```

Show deployment paths and container status:

```bash
sudo amas-env status
sudo amas-env paths
```

Edit the canonical file and regenerate derived files:

```bash
sudo amas-env edit canonical
sudo amas-env apply
```

Set one value without opening an editor:

```bash
sudo amas-env set LLM_PRIMARY_MODEL moderation-primary-v2
sudo amas-env apply
```

For a sensitive value, omit the value to receive a non-echoing prompt:

```bash
sudo amas-env set ANYTHINGLLM_API_KEY
```

The API key remains only in the root-owned canonical file and is not copied into `n8n.env`. Create the corresponding named credential in n8n separately.

Rotate all three AMAS tokens:

```bash
sudo amas-env rotate-tokens
```

After rotation, update any intake client or Promptfoo process that had cached an old token.

Validate and recreate the selected n8n services:

```bash
sudo amas-env apply
sudo amas-env verify
```

Create a configuration backup:

```bash
sudo amas-env backup
```

## Promptfoo

Load the generated environment before running the supplied suites:

```bash
set -a
source /etc/amas/promptfoo.env
set +a

cd /opt/amas-assessment-moderation-agent/evals
promptfoo eval -c promptfooconfig.yaml
promptfoo redteam run -c redteam.yaml
```

Alternatively, use Promptfoo's environment-file option when supported by the installed release.

## n8n credentials still required

Create and bind these credentials in the n8n UI using the exact names expected by the workflow exports:

### `AMAS PostgreSQL`

Use the dedicated AMAS application role and database. Do not point this credential at n8n's internal persistence role unless the database has been deliberately partitioned and reviewed.

### `AMAS AnythingLLM API`

Type: HTTP Header Auth.

```text
Header: Authorization
Value: Bearer <AnythingLLM developer API key>
```

### `AMAS LLM API`

Type: HTTP Header Auth.

```text
Header: Authorization
Value: Bearer <model-gateway API key>
```

The script keeps these API keys out of `n8n.env` so workflow authors cannot retrieve them through `$env`.

## Queue mode and task runners

The installer detects persistent containers using the same n8n image as the selected primary container. This normally includes queue workers and webhook processors.

External task-runner services may use a different image and are therefore not automatically selected. Review the deployment before adding a runner service to `--n8n-services`; doing so exposes the AMAS variables to that container. The supplied workflows should be refactored toward n8n credentials or an authenticated gateway before re-enabling environment blocking in a hardened deployment.

## Future n8n upgrades

The original Compose file is not edited. Therefore, an administrator who later recreates n8n using only the original Compose command can omit the AMAS override. After any n8n update, run:

```bash
sudo amas-env apply
sudo amas-env verify
```

This reapplies and verifies the managed override.

## Rollback

Remove the environment integration and recreate n8n using only its original Compose files:

```bash
sudo amas-env uninstall
```

The command does not delete workflows, PostgreSQL records, or stored assessment artefacts. It moves `/etc/amas` to a timestamped recovery directory and removes the management command.

To inspect the exact Compose action first:

```bash
sudo amas-env uninstall --dry-run --yes
```

## Security rationale

The override explicitly sets:

```text
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

This is required because the current AMAS workflow exports read selected values through `$env`. Restrict workflow-author access to trusted administrators. A production hardening phase should migrate authentication tokens and service secrets to n8n credentials or an external secrets/gateway mechanism and then restore environment blocking.
