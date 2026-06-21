# ADR-001: Bounded agentic orchestration

## Status

Accepted.

## Decision

Use deterministic workflow orchestration with narrowly scoped LLM specialists. The routing supervisor may select only allowlisted optional analyses. No model receives generic SQL, filesystem, email, HTTP browsing, or publication tools. The final disposition and approval boundary remain deterministic/human.

## Rationale

Assessment moderation combines formal invariants, contextual judgement, authoritative policy, and consequential institutional decisions. A fully autonomous agent would make permissions, provenance, testing, and appeals substantially harder to control.

## Consequences

- more workflows and contracts to maintain;
- clearer failure isolation and evaluation;
- lower excessive-agency risk;
- easier model substitution;
- human moderation remains mandatory.
