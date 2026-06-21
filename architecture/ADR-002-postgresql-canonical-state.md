# ADR-002: PostgreSQL as canonical state

## Status

Accepted.

## Decision

Use PostgreSQL as the source of truth for case state, prompts, traces, findings, reports, reviews, and audit events. AnythingLLM is a retrieval service; S3-compatible storage holds immutable binary/text objects.

## Rationale

Vector stores and workflow execution histories are unsuitable as the sole system of record. Relational constraints and versioned JSON provide auditable state while preserving analytical flexibility.
