# Security model and deployment checklist

AMAS processes assessment materials that may be confidential and may contain malicious instructions directed at AI systems. Treat the deployment as a security-sensitive internal application.

## Primary threats

### Indirect prompt injection

An uploaded brief, rubric, or retrieved document may contain text such as “ignore previous instructions,” instructions to call tools, or attempts to reveal system prompts. Controls implemented:

- deterministic pattern detection in preflight;
- system prompts that classify all submitted and retrieved text as untrusted data;
- no generic action tools exposed to specialist models;
- deterministic evidence verification;
- a critical injection finding produces `blocked_security`;
- red-team cases in Promptfoo.

Pattern detection is not complete protection. The strongest control is the absence of high-impact tools and the human approval boundary.

### Excessive agency

The LLM cannot directly:

- run arbitrary SQL;
- read arbitrary files;
- send email;
- publish reports;
- browse unrestricted URLs;
- alter policy sources;
- access another case by choosing an identifier.

All permitted actions are implemented by fixed workflows with typed inputs.

### Policy poisoning and obsolete authority

Controls implemented:

- a dedicated authoritative AnythingLLM workspace;
- source metadata including version, authority rank, effective dates, status, and hash;
- policy-source records in PostgreSQL;
- evidence verification against retrieved source and chunk identifiers;
- explicit escalation for policy conflicts.

Operationally, only authorised corpus administrators should publish or retire policy documents.

### Cross-case leakage

Case artifacts are stored and retrieved by server-controlled case IDs. Submitted documents are not embedded into the shared policy workspace. Production deployments should additionally enforce tenant scoping at the API gateway and, where multi-tenancy is real rather than nominal, PostgreSQL row-level security or separate databases.

### Data exfiltration

The model gateway and AnythingLLM should be reachable only over private networks or approved TLS endpoints. Block arbitrary outbound access from n8n workers. Contractually prohibit model providers from training on submitted data where required.

### Fabricated evidence

The evidence verifier rejects findings when:

- the artifact, learning outcome, preflight code, source ID, or policy chunk does not exist;
- a policy source was not retrieved;
- a cited excerpt lacks sufficient lexical support;
- a policy finding has no valid policy evidence.

Lexical matching is intentionally conservative and should be augmented with expert evaluation before production.

### Model drift and regression

Prompts, corpus version, workflow version, model aliases, input hashes, and execution IDs are recorded in report provenance. Run regression and red-team suites after any model, prompt, corpus, workflow, or retrieval change.

## Authentication zones

| Zone | Credential | Intended caller |
|---|---|---|
| Public case/report/review API | `AMAS_API_TOKEN` in the reference build | intake API / authorised clients |
| Internal workflow calls | `AMAS_INTERNAL_TOKEN` | n8n and intake API services |
| Evaluation endpoint | `AMAS_EVAL_TOKEN` | CI or Promptfoo only |
| PostgreSQL | `amas_app` | AMAS workflow nodes |
| Model gateway | `AMAS LLM API` credential | model HTTP nodes |
| AnythingLLM | `AMAS AnythingLLM API` credential | retrieval and ingestion nodes |

For production, replace static user-facing tokens with SSO/OIDC and scoped service identities. Rotate service tokens and keys. Never reuse the evaluation credential for production submission.

## Implemented controls

- cryptographic hashes for originals, extracted text, prompts, and reports;
- parameterized SQL queries;
- restricted database role for workflows;
- immutable report versioning;
- audit events for case receipt, preflight, report creation, and review;
- file-size and MIME allowlists;
- safe filename normalization;
- server-side S3 credentials;
- no credentials embedded in workflow exports;
- execution-data pruning;
- synthetic demonstration data;
- schema validation and CI checks.

## Controls requiring deployment work

The reference bundle does **not** claim to provide these automatically:

- university SSO, MFA, and role mapping;
- malware scanning of uploads;
- OCR for image-only PDFs;
- DLP/classification service;
- at-rest encryption configuration for managed storage;
- centralized SIEM and alerting;
- legal retention schedule;
- formal DPIA/privacy impact assessment;
- penetration testing;
- accessibility conformance testing;
- vendor data-processing agreements;
- model-provider residency and no-training guarantees;
- automatic key rotation;
- high availability and disaster recovery testing.

Add these before accepting real student, staff, HR, disciplinary, examination, or unpublished research data.

## n8n environment access

The reference workflows use `$env` in Code and expression fields. The Compose file therefore sets:

```text
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

This is convenient for a portable demonstration but broadens what workflow authors can read. Production hardening should:

1. move secret headers to n8n credentials or the gateway;
2. move non-secret configuration to controlled variables or database configuration;
3. restrict workflow-editing privileges;
4. re-enable environment blocking where the revised workflows permit it.

## Logging and trace privacy

n8n execution data can contain assessment text and model responses. The reference stack retains successful and failed execution data for seven days. Adjust this to institutional policy, and restrict access to n8n execution history. Do not log hidden chain-of-thought; AMAS records concise outputs, source evidence, usage, and tool/workflow traces instead.

## Pre-production security gate

Do not admit real data until all are true:

- TLS and trusted certificates are active;
- n8n editor is restricted;
- public API uses institutional identity and authorisation;
- internal webhooks are not internet-reachable;
- storage and database backups are encrypted and tested;
- model and AnythingLLM contracts are approved;
- corpus governance owners are named;
- retention/deletion policy is implemented;
- malware scanning and OCR decisions are implemented;
- red-team suite passes;
- a manual penetration test covers upload, auth, IDOR, SSRF, injection, and cross-case access;
- expert moderators have calibrated the outputs and false-critical rate.
