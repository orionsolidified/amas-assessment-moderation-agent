# Deployment guide

## Demonstration deployment

### Prerequisites

- Docker Engine with Compose v2;
- Python 3.11 or later for utility scripts;
- an AnythingLLM instance;
- an OpenAI-compatible model gateway;
- DNS/TLS if exposing the service beyond localhost.

### Procedure

```bash
python3 scripts/generate_secrets.py
$EDITOR deploy/.env
make validate
make up
```

Open n8n, complete first-user setup, create the three named credentials, then run:

```bash
make migrate
make prompts
make workflows
```

Publish workflows in the order listed in `N8N_WORKFLOW_MAP.md`.

Create the AnythingLLM workspace, then:

```bash
make policies
make demo
```

### Health checks

```bash
curl http://localhost:8080/health
curl http://localhost:5678/webhook/amas/health
```

Check PostgreSQL:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml \
  exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select * from amas.case_summary order by created_at desc limit 10;"
```

## Deployment to `agents.orionsolidified.io`

Recommended separation:

1. Terminate TLS at Caddy, Nginx, Traefik, or the existing platform gateway.
2. Route the public domain to `intake-api:8080`.
3. Keep the n8n editor on a separate restricted hostname or private network.
4. Set `WEBHOOK_URL` to the externally reachable n8n webhook origin.
5. Do not expose Garage's admin API or PostgreSQL.
6. Keep AnythingLLM and the model gateway private where possible.

An example is provided in `deploy/Caddyfile.example`.

## Institutional production changes

Replace the local components as follows:

| Reference component | Institutional replacement |
|---|---|
| Single-node Garage | managed S3 or replicated institutional object storage |
| Compose PostgreSQL | managed/HA PostgreSQL with PITR and TLS |
| Single-main n8n | queue mode and workers if concurrency requires it |
| Static API tokens | SSO/OIDC gateway, scoped service identities and rotation |
| Direct model API | approved gateway with logging, DLP and contract controls |
| Synthetic corpus | versioned, approved university/faculty policy corpus |
| Basic text extraction | approved document service, malware scan and OCR path |
| Local logs | centralized audit/SIEM with retention controls |

## Reverse proxy example

See `deploy/Caddyfile.example`. Protect the n8n editor using SSO, VPN, IP allowlists, or an identity-aware proxy. Tokens alone are not a complete administrative-access control.

## Upgrade process

1. Back up PostgreSQL, object storage, n8n workflows, and prompt manifests.
2. Regenerate workflows from source and run tests.
3. Deploy to a staging instance.
4. Run Promptfoo regression and red-team suites.
5. Compare expert-moderator calibration cases.
6. Publish workflow drafts only after review.
7. Retain the previous workflow and prompt versions for rollback.

Never use a floating `latest` tag in the production Compose file.
