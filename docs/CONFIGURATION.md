# Configuration

## Environment variables

The authoritative template is `deploy/.env.example`.

### Public routing

| Variable | Purpose |
|---|---|
| `N8N_HOST`, `N8N_PROTOCOL`, `N8N_PORT` | n8n runtime identity |
| `WEBHOOK_URL` | externally correct n8n webhook base URL |
| `N8N_INTERNAL_BASE_URL` | service-to-service n8n URL, normally `http://n8n:5678` |
| `AMAS_INTAKE_PUBLIC_URL` | browser-facing intake API |
| `AMAS_INTAKE_INTERNAL_URL` | service-to-service intake URL, normally `http://intake-api:8080` |

### Authentication tokens

`AMAS_API_TOKEN`, `AMAS_INTERNAL_TOKEN`, and `AMAS_EVAL_TOKEN` must be independent, high-entropy values. The evaluation token must not grant ordinary case submission or internal administration.

The reference workflows read these values from the n8n process environment in Code/HTTP nodes. This requires `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. For a hardened production deployment, move webhook authentication and self-call headers into n8n credentials or an authenticated API gateway, then re-enable environment blocking.

### PostgreSQL

The Compose stack uses the database owner for n8n's own persistence. AMAS workflow nodes must use the restricted `amas_app` role.

```text
host: postgres
port: 5432
database: POSTGRES_DB
user: amas_app
password: AMAS_APP_PASSWORD
SSL: disabled only on the private Compose network
```

For managed PostgreSQL, require TLS, restrict source networks, enable automated backups, and use a connection pool.

### Model gateway

`LLM_BASE_URL` must expose an OpenAI-compatible endpoint:

```text
POST {LLM_BASE_URL}/chat/completions
```

The workflows send:

- a model alias;
- system and user messages;
- temperature and token limits;
- `response_format: {"type": "json_object"}`.

Configure stable aliases:

```text
LLM_PRIMARY_MODEL=moderation-primary
LLM_CRITIC_MODEL=moderation-critic
```

Use a separate critic model or provider where practical. A critic routed to the identical model and prompt family provides weaker independence.

### AnythingLLM

Create a dedicated developer API key and a dedicated workspace. The credential named `AMAS AnythingLLM API` must send:

```text
Authorization: Bearer <key>
```

The workflow uses:

```text
POST /api/v1/workspace/{slug}/vector-search
POST /api/v1/document/raw-text
POST /api/v1/workspace/{slug}/update-embeddings
```

AnythingLLM exposes the exact API contract of the installed version at `/api/docs`. Verify request and response fields there before institutional deployment; the normalizer already tolerates common `result`, `results`, and `documents` response shapes.

### Object storage

The intake API uses standard S3 parameters:

```text
S3_ENDPOINT
S3_REGION
S3_BUCKET
S3_ACCESS_KEY
S3_SECRET_KEY
```

Use path-style-compatible endpoints where required. Restrict the key to the AMAS bucket and prefixes in `storage/s3-iam-policy.json`.

## Named n8n credentials

### `AMAS PostgreSQL`

Type: PostgreSQL. Use the restricted application role.

### `AMAS LLM API`

Type: HTTP Header Auth.

```text
Name: Authorization
Value: Bearer <gateway token>
```

### `AMAS AnythingLLM API`

Type: HTTP Header Auth.

```text
Name: Authorization
Value: Bearer <AnythingLLM API key>
```

## Production domain pattern

A safe pattern for the user's infrastructure is:

```text
agents.orionsolidified.io       -> intake API only
automation.orionsolidified.io   -> n8n editor and webhooks, restricted to staff/VPN/SSO
anythingllm.internal            -> private service
model-gateway.internal          -> private service
```

The public intake API proxies requests to n8n, so the n8n editor does not need to be generally accessible.
