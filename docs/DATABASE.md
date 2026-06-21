# PostgreSQL design

## Roles

- `POSTGRES_USER`: database owner used by n8n's own persistence and migrations.
- `amas_app`: restricted read/write role for AMAS workflow nodes.
- `amas_readonly`: audit/reporting role.

Do not configure workflow PostgreSQL nodes with the database-owner account.

## Main tables

| Table | Purpose |
|---|---|
| `amas.cases` | case metadata and lifecycle state |
| `amas.artifacts` | original object references, hashes and extracted text |
| `amas.learning_outcomes` | approved outcomes supplied for the case |
| `amas.prompt_versions` | immutable prompt bodies, schemas and model configuration |
| `amas.policy_sources` | authoritative source metadata and AnythingLLM location |
| `amas.preflight_runs` | deterministic facts and findings |
| `amas.retrieval_runs` | retrieval requests, raw responses and accepted chunks |
| `amas.agent_runs` | model requests, responses, parsed outputs, usage and latency |
| `amas.findings` | report-linked canonical findings |
| `amas.reports` | immutable versioned canonical report JSON |
| `amas.review_actions` | human decisions and amendments |
| `amas.audit_events` | append-only operational/governance events |
| `amas.evaluation_*` | evaluation cases, runs and results |

## Case status state model

```text
received
  -> normalised
  -> preflight
  -> analysing
  -> awaiting_review
  -> approved | approved_with_changes | rejected
```

`failed` and `archived` are available for operational and retention workflows.


## Integrity and concurrency controls

- `amas.cases.input_sha256` binds each case ID to the canonical normalized submission. `amas.enforce_immutable_input` rejects attempts to mutate an existing case.
- Revised assessment packages use a new case ID and may retain the same `external_ref`.
- Canonical report creation acquires a transaction-scoped advisory lock keyed by case ID before calculating the next report version. This prevents concurrent runs from assigning the same version number.
- Reports and findings are append-only at the application layer. Reviewer decisions are stored separately in `review_actions` rather than rewriting model evidence.

## Migrations

For a fresh Compose volume, files under `sql/` run automatically. For an existing volume:

```bash
./scripts/apply_migrations.sh
```

The scripts are idempotent where practical. Review every migration in staging before production.

## Useful views/functions

- `amas.case_summary`: latest disposition and report version by case;
- `amas.case_bundle(uuid)`: case, artifacts, outcomes, latest preflight and report;
- `amas.next_report_version(uuid)`: next immutable report version;
- `amas.append_audit(...)`: append an audit event.

## Data integrity

- case IDs and report IDs are UUIDs;
- report versions are unique per case;
- prompt key/version pairs are unique, with one active version per key;
- policy source/version pairs are unique;
- reports store SHA-256 hashes;
- artifacts store original and extracted-text hashes;
- findings are linked to the report version that created them.

## Production recommendations

- TLS and certificate verification;
- automated backups and point-in-time recovery;
- connection pooling;
- database-level monitoring;
- separate n8n and AMAS databases or schemas where operational policy requires it;
- row-level security or physical tenant separation for genuine multi-tenancy;
- immutable/append-only controls for audit data where required;
- a tested archival and deletion procedure.
