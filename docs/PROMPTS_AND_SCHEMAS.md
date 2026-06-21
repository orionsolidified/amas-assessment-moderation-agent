# Prompts and structured contracts

## Prompt release model

Each analytical role has:

- a versioned system prompt;
- a user-template prompt;
- a JSON output schema;
- model configuration;
- a content hash;
- one active database version.

The manifest is `prompts/manifest.json`. Load it with:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml run --rm bootstrap
```

## Shared controls

`prompts/_shared_system.md` defines:

- the non-approval authority boundary;
- untrusted document treatment;
- evidence requirements;
- policy conflict behavior;
- severity calibration;
- JSON-only output;
- prohibition on hidden-reasoning disclosure.

## Roles

| Prompt key | Function |
|---|---|
| `assessment_profiler` | classifies task and selects allowlisted optional specialists |
| `outcome_alignment` | maps observable evidence to learning outcomes |
| `rubric_quality` | checks criterion quality, weighting and descriptor distinctions |
| `assessment_validity` | evaluates construct validity, authenticity and workload |
| `ai_use_design` | recommends Closed, Guided or Open AI conditions |
| `policy_accessibility` | checks policy support, clarity, equity and avoidable barriers |
| `programming_assessment` | examines code/process evidence, testing, security and viva design |
| `group_work` | examines individual contribution and fairness in collective work |
| `adversarial_critic` | challenges verified findings and missing analyses |
| `report_synthesis` | drafts the narrative report before deterministic finalization |

## Why the model does not own the final report

The synthesis model may draft the executive summary, scorecard and AI-use design. A deterministic Code node then:

- restores the canonical verified findings;
- applies critic actions;
- deduplicates findings;
- recalculates disposition;
- ensures provenance;
- prevents model-generated findings from bypassing verification.

## Schema contracts

- `intake.schema.json`: normalized case input;
- `profiler-output.schema.json`: routing decision;
- `specialist-output.schema.json`: findings, uncertainties and metrics;
- `critic-output.schema.json`: finding reviews and systemic gaps;
- `report.schema.json`: canonical report;
- `review.schema.json`: human review action.

JSON mode is treated as a transport aid, not semantic validation. Code nodes normalize enums, required arrays, confidence bounds, and finding identifiers.

## Prompt change discipline

Never edit prompts directly in the database. Change source, increment version, run tests, load into staging, evaluate, then promote. Retain the prior version for rollback and provenance.
