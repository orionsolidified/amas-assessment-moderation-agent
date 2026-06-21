# Authoritative knowledge corpus

The quality of policy moderation depends on corpus governance, not merely embedding quality.

## Workspace rule

Use one dedicated AnythingLLM workspace for **active, approved, authoritative documents**. Do not upload:

- assessment briefs being moderated;
- archived policy versions without an explicit inactive status;
- personal notes;
- unapproved draft guidance;
- blog posts or vendor marketing;
- student data.

## Required metadata

Each source must have:

```json
{
  "source_id": "POL-ASSESS-004",
  "title": "Faculty Assessment and Moderation Policy",
  "version": "3.2",
  "authority_rank": 80,
  "authority_scope": "faculty",
  "status": "active",
  "effective_from": "2026-01-01",
  "effective_to": null,
  "sha256": "...",
  "locator": "section or whole document"
}
```

## Suggested authority order

| Authority | Example rank |
|---|---:|
| Law/regulator/qualification authority | 120 |
| University regulation | 100 |
| Senate-approved university policy | 90 |
| Faculty policy | 80 |
| Department procedure | 60 |
| Programme guidance | 40 |
| Module convention | 20 |

Rank does not permit the model to invent conflict resolution. A material contradiction must be reported for human adjudication.

## Ingestion process

1. Verify approval status and owner.
2. Record version and effective dates.
3. Hash the source file.
4. Store the original in approved object storage.
5. Extract and inspect text.
6. Ingest via workflow 90.
7. Run smoke-test retrieval queries.
8. Increment `AMAS_CORPUS_VERSION`.
9. Run regression cases.
10. Retire superseded versions and confirm they no longer appear in active retrieval.

The included script ingests only the synthetic demonstration corpus:

```bash
python3 scripts/ingest_demo_policies.py
```

## Retrieval quality tests

Maintain at least one expected query for every important policy clause. Record:

- expected source ID;
- expected section/locator;
- minimum acceptable rank in top-k;
- false-positive sources that must not outrank the authority;
- multilingual variants where relevant.

## Sinhala, Tamil, and English

Do not assume equivalent retrieval performance. Test policy wording, module terminology, and common lecturer queries in all languages used institutionally. Consider a multilingual embedding model and preserve the authoritative source language and approved translations.
