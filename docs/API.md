# API reference

The browser-facing service is the FastAPI application on port `8080`. It proxies normalised requests to n8n and keeps S3 credentials server-side.

## Authentication

Reference deployment header:

```http
X-AMAS-API-Token: <AMAS_API_TOKEN>
```

Production should replace this with institutional identity and authorisation.

## Health

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "n8n_base_url": "http://n8n:5678",
  "s3_bucket": "amas"
}
```

## Case identity and revisions

A `case_id` identifies one immutable submission snapshot. The database stores a canonical SHA-256 digest of the complete normalized input. Repeating the same payload with the same `case_id` is permitted, although the synchronous reference workflow may create another report version. Changing the brief, rubric, outcomes, or metadata under an existing `case_id` is rejected.

Submit a revised assessment with a new `case_id`; use `external_ref` to associate related versions in an institutional system. Tenant identity must be derived from authenticated context in production rather than trusted from a client-supplied field.

## Submit normalized JSON

```http
POST /v1/cases/json
Content-Type: application/json
X-AMAS-API-Token: ...
```

The payload must conform to `schemas/intake.schema.json`. See `samples/demo_case.json`.

Example:

```bash
curl -sS \
  -H "X-AMAS-API-Token: $AMAS_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @samples/demo_case.json \
  "$AMAS_INTAKE_PUBLIC_URL/v1/cases/json"
```

The call is synchronous in the reference implementation and may take several minutes depending on the selected models. Production deployments should consider asynchronous submission and status polling.

## Submit files

```http
POST /v1/cases
Content-Type: multipart/form-data
```

Parts:

- `metadata`: JSON string containing case fields and learning outcomes;
- `assessment_brief`: required file;
- `rubric`: required file;
- `module_descriptor`: optional file;
- `supporting_documents`: repeatable optional files.

Allowed formats:

- PDF;
- DOCX;
- text/plain;
- Markdown;
- HTML;
- simple RTF.

Image-only PDFs return `ocr_required`; the system does not silently perform OCR.

## Retrieve latest report

```http
GET /v1/cases/{case_id}/report
X-AMAS-API-Token: ...
```

Response contains the case status, report ID, version, canonical report, and creation time.

## Record a human review action

```http
POST /v1/reviews
Content-Type: application/json
X-AMAS-API-Token: ...
```

```json
{
  "case_id": "a10c2010-1111-4b22-8333-111111111111",
  "report_id": "00000000-0000-0000-0000-000000000000",
  "finding_id": null,
  "reviewer_id": "staff-1234",
  "decision": "accept_with_amendments",
  "comment": "Rubric corrected and individual viva added.",
  "changes": {
    "rubric_total": 100,
    "individual_evidence": ["repository history", "viva"]
  }
}
```

Allowed decisions:

```text
accept
accept_with_amendments
dismiss
request_rerun
escalate
approve
reject
```

Only `approve` and `reject` represent a report-level final action in the reference workflow. Institution-specific role checks must be added at the identity layer.

## Internal report archive

```http
POST /internal/reports
X-AMAS-Internal-Token: ...
```

This endpoint is for n8n only. It writes canonical report JSON under:

```text
reports/{tenant_id}/{case_id}/v{version}-{sha256}.json
```

Do not expose it publicly.

## Direct n8n endpoints

The n8n webhook paths are listed in `N8N_WORKFLOW_MAP.md`. Clients should ordinarily use the FastAPI service, not direct n8n URLs.
