# n8n workflow map

## Publication order

Publish internal dependencies before the public entry points.

| Order | File | Workflow | Webhook |
|---:|---|---|---|
| 1 | `00_health.json` | Health | `GET /webhook/amas/health` |
| 2 | `02_deterministic_preflight.json` | Deterministic preflight | `POST /webhook/amas/internal/preflight` |
| 3 | `03_policy_retrieval.json` | AnythingLLM retrieval | `POST /webhook/amas/internal/policy-retrieval` |
| 4 | `09_assessment_profiler.json` | Routing supervisor | `POST /webhook/amas/internal/profile` |
| 5 | `10_outcome_alignment.json` | Outcome alignment | `POST /webhook/amas/internal/specialist/outcome-alignment` |
| 6 | `11_rubric_quality.json` | Rubric quality | `POST /webhook/amas/internal/specialist/rubric-quality` |
| 7 | `12_assessment_validity.json` | Assessment validity | `POST /webhook/amas/internal/specialist/assessment-validity` |
| 8 | `13_ai_use_design.json` | AI-use design | `POST /webhook/amas/internal/specialist/ai-use-design` |
| 9 | `14_policy_accessibility.json` | Policy and accessibility | `POST /webhook/amas/internal/specialist/policy-accessibility` |
| 10 | `15_programming_assessment.json` | Programming assessment | `POST /webhook/amas/internal/specialist/programming-assessment` |
| 11 | `16_group_work.json` | Group work | `POST /webhook/amas/internal/specialist/group-work` |
| 12 | `21_evidence_verifier.json` | Evidence verifier | `POST /webhook/amas/internal/evidence-verifier` |
| 13 | `22_adversarial_critic.json` | Critic | `POST /webhook/amas/internal/critic` |
| 14 | `23_report_synthesis.json` | Synthesis and persistence | `POST /webhook/amas/internal/synthesize` |
| 15 | `20_moderation_orchestrator.json` | Root orchestrator | `POST /webhook/amas/internal/orchestrate` |
| 16 | `90_knowledge_ingestion.json` | Policy ingestion | `POST /webhook/amas/internal/knowledge/ingest` |
| 17 | `31_report_api.json` | Report retrieval | `GET /webhook/amas/v1/cases/:caseId/report` |
| 18 | `30_human_review.json` | Human review | `POST /webhook/amas/v1/reviews` |
| 19 | `01_case_intake.json` | Public case intake | `POST /webhook/amas/v1/cases` |
| 20 | `40_promptfoo_evaluation_endpoint.json` | Evaluation target | `POST /webhook/amas/eval/moderate` |

## Credential assignments

After import:

- assign `AMAS PostgreSQL` to every PostgreSQL node;
- assign `AMAS LLM API` to model-gateway HTTP nodes;
- assign `AMAS AnythingLLM API` to AnythingLLM HTTP nodes.

The workflow JSON intentionally contains placeholder credential IDs. The exact names permit fast reassignment but do not import secret material.

## Core orchestration trace

The root workflow executes:

```text
Load case
  -> deterministic preflight
  -> policy retrieval
  -> profiling supervisor
  -> mandatory + allowlisted optional specialists
  -> deterministic evidence verification
  -> independent critic
  -> canonical synthesis and disposition recalculation
  -> PostgreSQL report version
  -> object-storage archive
```

## Workflow regeneration

Do not hand-edit generated JSON without also updating `scripts/generate_workflows.py`.

```bash
python3 scripts/generate_workflows.py
python3 scripts/validate_bundle.py
pytest -q
```
