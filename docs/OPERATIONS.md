# Operations

## Daily checks

- intake API and n8n health;
- PostgreSQL storage and connection health;
- object-storage availability;
- failed n8n executions;
- model-gateway error and latency rates;
- AnythingLLM retrieval failures;
- cases stuck in `analysing` or `preflight`;
- reports awaiting human review beyond the agreed service level.

Useful query:

```sql
SELECT status, count(*)
FROM amas.cases
GROUP BY status
ORDER BY status;
```

## Trace a case

```sql
SELECT * FROM amas.case_summary WHERE id = '<case-uuid>';
SELECT * FROM amas.preflight_runs WHERE case_id = '<case-uuid>' ORDER BY started_at;
SELECT specialist_key, status, model, latency_ms, input_tokens, output_tokens
FROM amas.agent_runs WHERE case_id = '<case-uuid>' ORDER BY started_at;
SELECT * FROM amas.reports WHERE case_id = '<case-uuid>' ORDER BY report_version;
SELECT * FROM amas.review_actions WHERE case_id = '<case-uuid>' ORDER BY created_at;
SELECT * FROM amas.audit_events WHERE case_id = '<case-uuid>' ORDER BY event_time;
```

## Prompt release

1. Edit prompt source files.
2. Increment the prompt version in `prompts/manifest.json`.
3. Run tests.
4. Load prompts into staging.
5. Run regression and expert calibration.
6. Promote the prompt version by loading it into production.

`load_prompts.py` deactivates the previous version for a prompt key but preserves it for audit.

## Corpus release

Increment `AMAS_CORPUS_VERSION` whenever active embedded content, splitting, embedding model, reranker, or policy status changes materially.

## Backups

```bash
./scripts/backup.sh
```

Back up:

- PostgreSQL custom dump;
- Garage data for the local profile;
- n8n workflow exports;
- environment and credential escrow through an approved secrets process;
- AnythingLLM workspace/database according to its deployment method.

Test restoration at a defined interval. A backup that has not been restored is not evidence of recoverability.

## Retention

Suggested classes to decide institutionally:

| Data | Example decision |
|---|---|
| Original assessment package | duration of moderation and appeals window |
| Canonical report and review record | institutional quality-assurance retention |
| n8n execution payloads | short operational period, e.g. days rather than years |
| Evaluation artifacts | short-lived unless part of a release record |
| Audit events | security and governance schedule |
| Obsolete policy embeddings | remove from active workspace; retain source in archive |

The included S3 lifecycle expires `evals/` objects after 30 days and aborts stale multipart uploads. It does not impose an institutional retention policy for originals or reports.

## Incident response

For suspected data exposure or malicious upload:

1. disable public intake;
2. preserve relevant logs and hashes;
3. rotate affected service credentials;
4. block outbound model calls if required;
5. identify affected case IDs and object keys;
6. follow institutional security and data-protection notification procedures;
7. do not delete evidence until authorised;
8. patch, regression-test, and document the corrective release.
