\set ON_ERROR_STOP on

-- Metadata placeholders for the synthetic workshop corpus. Workflow 90 replaces
-- the hashes and AnythingLLM locations when the actual documents are ingested.
INSERT INTO amas.policy_sources
  (source_id, title, version, authority_rank, authority_scope, status, effective_from, sha256, metadata)
VALUES
  ('UNIV-ASSESS-001', 'Synthetic University Assessment and Moderation Policy', '1.0-demo', 100, 'university', 'active', CURRENT_DATE, repeat('0',64), '{"synthetic":true,"demo_only":true,"ingestion_pending":true}'::jsonb),
  ('FAC-AI-002', 'Synthetic Faculty Guidance on Generative AI in Assessment', '1.1-demo', 80, 'faculty', 'active', CURRENT_DATE, repeat('1',64), '{"synthetic":true,"demo_only":true,"ingestion_pending":true}'::jsonb),
  ('ACCESS-003', 'Synthetic Accessible Assessment Design Standard', '1.0-demo', 70, 'university', 'active', CURRENT_DATE, repeat('2',64), '{"synthetic":true,"demo_only":true,"ingestion_pending":true}'::jsonb)
ON CONFLICT (source_id, version) DO NOTHING;
