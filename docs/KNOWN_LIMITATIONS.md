# Known limitations

## Reference implementation status

The bundle is complete enough to deploy and demonstrate, but it is not a production certification or a substitute for institutional governance.

## Document processing

- PDF extraction handles embedded text only; image-only PDFs are flagged `ocr_required`.
- Complex tables, diagrams, mathematical notation, and scanned rubrics may not extract reliably.
- RTF extraction is intentionally basic.
- No malware scanner is included in the default stack.
- MIME validation relies on the upload's declared media type and extension rather than full magic-byte classification.

## Retrieval

- AnythingLLM endpoint details must be verified against the installed instance's `/api/docs`.
- Vector retrieval may omit relevant clauses or rank a weak clause highly.
- The deterministic verifier checks source identity and lexical support, not legal interpretation.
- Authority conflicts still require humans.

## Model behavior

- JSON mode does not guarantee semantic validity.
- The primary and critic models may share failure modes.
- Confidence is model calibration metadata, not a statistical probability.
- Specialist analyses may vary across reruns.
- The included prompts have not been calibrated against a real university moderation dataset.

## Workflow execution

- The reference intake path is synchronous.
- Specialist dispatch uses n8n item fan-out; very high concurrency requires queue-mode architecture.
- Static tokens are used in the demonstration profile.
- Environment access is enabled in n8n nodes for portability.
- Object-archive failure is returned as a warning while PostgreSQL retains the canonical report; automatic retry and operational alerting still require deployment work.

## Academic scope

- The system supports pre-release assessment design moderation only.
- It does not moderate marked student work.
- It does not establish misconduct.
- It does not validate discipline-specific professional accreditation by default.
- Accessibility findings are design observations, not individual accommodation decisions.
- Sinhala and Tamil behavior requires dedicated corpus and model evaluation.

## Governance

- Role-based approval is not fully implemented in the reference API.
- Tenant isolation is logical, not a completed multi-tenant security architecture.
- Data-retention periods are placeholders requiring institutional decision.
- Legal and policy examples are synthetic and must not be treated as university policy.
