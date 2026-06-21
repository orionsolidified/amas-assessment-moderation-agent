# Testing and evaluation

## Static bundle tests

```bash
python3 scripts/validate_bundle.py
pytest -q
```

Coverage includes:

- JSON and YAML parsing;
- workflow graph integrity and unique webhook paths;
- sample intake and report schema validation;
- prompt-manifest completeness;
- credential-secret hygiene;
- absence of generic high-risk nodes;
- Compose environment completeness.

## Promptfoo regression suite

```bash
./scripts/run_evals.sh
```

The reference cases cover:

- clean individual portfolio;
- rubric total of 110;
- indirect prompt injection;
- group mark with no individual evidence;
- unassessed security outcome.

Add institution-specific golden cases reviewed independently by at least two experienced moderators.

## Recommended release gates

These are targets to validate, not claims about the uncalibrated bundle:

| Metric | Suggested gate |
|---|---:|
| Report-schema validity | 100% |
| Deterministic arithmetic detection | 100% |
| Unauthorized write actions | 0 |
| Cross-case retrieval | 0 |
| Valid policy source/chunk references | ≥98% |
| Recall of known major findings | ≥90% |
| False-critical rate | <5% |
| Expert disposition agreement | ≥85% |
| Critical findings receiving human review | 100% |

## Evaluation strata

Maintain separate sets for:

- deterministic defects;
- pedagogical validity;
- policy compliance;
- accessibility/equity;
- programming assessments;
- group assessment;
- multilingual cases;
- adversarial documents;
- missing or conflicting evidence;
- clean cases that test false-positive control.

## Model comparison

Do not select a model using average quality alone. Compare:

- high-severity recall and false positives;
- evidence faithfulness;
- structured-output failure rate;
- multilingual performance;
- latency and cost;
- refusal behavior;
- susceptibility to injected document instructions;
- consistency across reruns.

## Human calibration

For each golden case, retain:

- expert findings;
- severity;
- acceptable alternative interpretations;
- expected disposition range;
- policy citations;
- adjudication notes.

Measure inter-rater agreement before treating expert labels as a single unquestionable ground truth.
