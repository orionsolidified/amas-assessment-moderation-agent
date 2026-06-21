# Live demonstration runbook

## Objective

Demonstrate the transition from a persuasive chatbot response to a bounded, traceable, evaluated agentic system.

## Preparation

Complete at least one day before the session:

1. Publish all workflows.
2. Confirm named credentials are bound.
3. Verify n8n, PostgreSQL, object storage, AnythingLLM, and model gateway health.
4. Ingest the synthetic policies.
5. Submit the demo once and retain the successful execution IDs.
6. Run Promptfoo regression tests.
7. Confirm the live case contains no real student data.
8. Keep `samples/sample_report.json` available as a fallback display.

## Demonstration case

Use `samples/demo_case.json`. It contains six planted issues:

1. rubric allocations total 110;
2. assessment metadata says 30%, while the brief says 40%;
3. LO3 on security is not assessed;
4. all marks are collective and no individual evidence is required;
5. AI use is prohibited without a defensible design rationale;
6. an embedded instruction attempts indirect prompt injection.

## Suggested 25-minute sequence

### 1. Submit the case — 2 minutes

```bash
./scripts/submit_demo.sh
```

Show the case ID and explain that originals are hashed and stored before model analysis.

### 2. Deterministic preflight — 4 minutes

Open workflow 02's execution and show:

- 110-mark calculation;
- weighting conflict;
- LO reference check;
- prompt-injection indicator.

Ask participants which checks should never be delegated to an LLM.

### 3. Retrieval — 3 minutes

Open workflow 03 and inspect:

- bounded queries;
- top-k results;
- source IDs, chunk IDs, scores, authority metadata;
- corpus version.

Emphasise that RAG supplies evidence; it does not guarantee correct reasoning.

### 4. Agentic routing — 3 minutes

Open workflow 09 and the root orchestrator. Show that:

- five specialists are mandatory;
- `programming_assessment` is selected because executable software is assessed;
- `group_work` is selected because collective marks are material;
- routing is allowlisted.

### 5. Specialist outputs — 4 minutes

Compare outcome alignment, rubric quality, and AI-use design. Point out the separation of observation, interpretation, recommendation, evidence, severity, and confidence.

### 6. Evidence verifier and critic — 4 minutes

Show one finding that survives verification and, ideally, one that is rejected or downgraded. Explain that a second model is not a proof mechanism; deterministic source checks remain necessary.

### 7. Canonical report and human boundary — 3 minutes

Show:

- deterministic final disposition;
- report provenance;
- report version and hash;
- object-storage archive;
- human review API.

Record an `accept_with_amendments` action, not an autonomous approval.

### 8. Evals — 2 minutes

Show the Promptfoo suite covering:

- valid report contract;
- rubric arithmetic;
- prompt injection;
- group individual evidence;
- unassessed outcomes.

## Discussion prompts

- Which findings require policy evidence rather than pedagogical judgement?
- What would be a dangerous tool to expose to this agent?
- Which data should never enter a consumer model?
- What error rate is acceptable for a recommendation system that cannot approve?
- How would the evaluation set change for nursing, law, management, or humanities?

## Fallback plan

If a model or external service is unavailable:

- show the previously successful n8n execution;
- use `samples/sample_report.json`;
- run deterministic preflight locally from the stored execution;
- discuss the failure boundary as part of the lesson.

Do not hide service failure. Reliability and fallback are central advanced topics.
