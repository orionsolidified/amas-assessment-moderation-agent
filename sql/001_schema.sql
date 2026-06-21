\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS amas;

DO $$ BEGIN
  CREATE TYPE amas.case_status AS ENUM (
    'received','normalised','preflight','analysing','awaiting_review',
    'approved','approved_with_changes','rejected','failed','archived'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE amas.artifact_type AS ENUM (
    'assessment_brief','rubric','module_descriptor','programme_specification',
    'policy','supporting_document','generated_report'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE amas.finding_severity AS ENUM ('info','minor','major','critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE amas.report_disposition AS ENUM (
    'ready_for_human_approval','minor_revision','major_revision',
    'insufficient_evidence','policy_conflict_requires_review','blocked_security'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE amas.review_decision AS ENUM (
    'accept','accept_with_amendments','dismiss','request_rerun','escalate','approve','reject'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS amas.cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_ref TEXT,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  title TEXT NOT NULL,
  module_code TEXT,
  module_title TEXT,
  study_level TEXT,
  credit_value NUMERIC(8,2),
  assessment_weight NUMERIC(8,2),
  assessment_type TEXT,
  individual_or_group TEXT,
  formative_or_summative TEXT,
  issue_date DATE,
  submission_date DATE,
  submitter_id TEXT,
  moderator_id TEXT,
  declared_ai_mode TEXT,
  evaluation_mode BOOLEAN NOT NULL DEFAULT FALSE,
  status amas.case_status NOT NULL DEFAULT 'received',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  input_sha256 TEXT NOT NULL,
  latest_report_id UUID,
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS amas.artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  artifact_type amas.artifact_type NOT NULL,
  original_filename TEXT,
  mime_type TEXT,
  size_bytes BIGINT,
  storage_bucket TEXT,
  storage_key TEXT,
  sha256 TEXT,
  extracted_text TEXT,
  text_sha256 TEXT,
  extraction_status TEXT NOT NULL DEFAULT 'provided',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (case_id, artifact_type, sha256)
);

CREATE TABLE IF NOT EXISTS amas.learning_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  outcome_code TEXT NOT NULL,
  description TEXT NOT NULL,
  level_descriptor TEXT,
  source_artifact_id UUID REFERENCES amas.artifacts(id) ON DELETE SET NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (case_id, outcome_code)
);

CREATE TABLE IF NOT EXISTS amas.prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_key TEXT NOT NULL,
  version TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  user_template TEXT NOT NULL,
  output_schema JSONB NOT NULL,
  model_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  content_sha256 TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (prompt_key, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS prompt_versions_one_active
  ON amas.prompt_versions(prompt_key) WHERE active;

CREATE TABLE IF NOT EXISTS amas.policy_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  version TEXT NOT NULL,
  authority_rank INTEGER NOT NULL,
  authority_scope TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  effective_from DATE,
  effective_to DATE,
  anythingllm_doc_location TEXT,
  storage_bucket TEXT,
  storage_key TEXT,
  sha256 TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_id, version)
);

CREATE TABLE IF NOT EXISTS amas.preflight_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  workflow_version TEXT NOT NULL,
  status TEXT NOT NULL,
  facts JSONB NOT NULL DEFAULT '{}'::jsonb,
  findings JSONB NOT NULL DEFAULT '[]'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  n8n_execution_id TEXT,
  error JSONB
);

CREATE TABLE IF NOT EXISTS amas.retrieval_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID REFERENCES amas.cases(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  corpus_version TEXT,
  workspace_slug TEXT,
  request JSONB NOT NULL,
  response JSONB NOT NULL,
  accepted_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  n8n_execution_id TEXT
);

CREATE TABLE IF NOT EXISTS amas.agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  specialist_key TEXT NOT NULL,
  prompt_version_id UUID REFERENCES amas.prompt_versions(id),
  model TEXT,
  model_provider TEXT,
  request_hash TEXT,
  request JSONB NOT NULL,
  response JSONB,
  parsed_output JSONB,
  status TEXT NOT NULL DEFAULT 'started',
  latency_ms INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  estimated_cost NUMERIC(14,6),
  n8n_execution_id TEXT,
  error JSONB,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS amas.findings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  report_id UUID,
  agent_run_id UUID REFERENCES amas.agent_runs(id) ON DELETE SET NULL,
  finding_ref TEXT,
  code TEXT NOT NULL,
  category TEXT NOT NULL,
  severity amas.finding_severity NOT NULL,
  observation TEXT NOT NULL,
  interpretation TEXT,
  recommendation TEXT,
  confidence NUMERIC(5,4),
  human_judgment_required BOOLEAN NOT NULL DEFAULT TRUE,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  critic_status TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT findings_id_report_case_unique UNIQUE (id, report_id, case_id)
);
CREATE INDEX IF NOT EXISTS findings_case_idx ON amas.findings(case_id, severity);

CREATE TABLE IF NOT EXISTS amas.reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  report_version INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  disposition amas.report_disposition NOT NULL,
  report JSONB NOT NULL,
  report_sha256 TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  prompt_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
  corpus_version TEXT,
  model_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
  storage_bucket TEXT,
  storage_key TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT reports_case_version_unique UNIQUE (case_id, report_version),
  CONSTRAINT reports_id_case_unique UNIQUE (id, case_id)
);

ALTER TABLE amas.findings
  DROP CONSTRAINT IF EXISTS findings_report_fk;
ALTER TABLE amas.findings
  ADD CONSTRAINT findings_report_fk
  FOREIGN KEY (report_id) REFERENCES amas.reports(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS findings_report_idx ON amas.findings(report_id);

ALTER TABLE amas.cases
  DROP CONSTRAINT IF EXISTS cases_latest_report_fk;
ALTER TABLE amas.cases
  ADD CONSTRAINT cases_latest_report_fk
  FOREIGN KEY (latest_report_id) REFERENCES amas.reports(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS amas.review_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES amas.cases(id) ON DELETE CASCADE,
  report_id UUID NOT NULL REFERENCES amas.reports(id) ON DELETE CASCADE,
  finding_id UUID REFERENCES amas.findings(id) ON DELETE SET NULL,
  reviewer_id TEXT NOT NULL,
  decision amas.review_decision NOT NULL,
  comment TEXT,
  changes JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE amas.review_actions
  DROP CONSTRAINT IF EXISTS review_actions_report_case_fk;
ALTER TABLE amas.review_actions
  ADD CONSTRAINT review_actions_report_case_fk
  FOREIGN KEY (report_id, case_id) REFERENCES amas.reports(id, case_id) ON DELETE CASCADE;

ALTER TABLE amas.review_actions
  DROP CONSTRAINT IF EXISTS review_actions_finding_scope_fk;
ALTER TABLE amas.review_actions
  ADD CONSTRAINT review_actions_finding_scope_fk
  FOREIGN KEY (finding_id, report_id, case_id) REFERENCES amas.findings(id, report_id, case_id) ON DELETE SET NULL (finding_id);

CREATE TABLE IF NOT EXISTS amas.audit_events (
  id BIGSERIAL PRIMARY KEY,
  event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  case_id UUID,
  actor_type TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  object_type TEXT,
  object_id TEXT,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  correlation_id TEXT,
  n8n_execution_id TEXT
);
CREATE INDEX IF NOT EXISTS audit_case_time_idx ON amas.audit_events(case_id, event_time DESC);

CREATE TABLE IF NOT EXISTS amas.evaluation_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  payload JSONB NOT NULL,
  expected JSONB NOT NULL,
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS amas.evaluation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  suite_name TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  prompt_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
  model_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS amas.evaluation_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_run_id UUID NOT NULL REFERENCES amas.evaluation_runs(id) ON DELETE CASCADE,
  evaluation_case_id UUID REFERENCES amas.evaluation_cases(id) ON DELETE SET NULL,
  eval_key TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  score NUMERIC(8,5),
  assertions JSONB NOT NULL DEFAULT '[]'::jsonb,
  output JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION amas.touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS cases_touch_updated_at ON amas.cases;
CREATE TRIGGER cases_touch_updated_at
BEFORE UPDATE ON amas.cases
FOR EACH ROW EXECUTE FUNCTION amas.touch_updated_at();

CREATE OR REPLACE VIEW amas.case_summary AS
SELECT
  c.id,
  c.external_ref,
  c.title,
  c.module_code,
  c.status,
  c.evaluation_mode,
  c.created_at,
  c.updated_at,
  r.disposition,
  r.report_version,
  r.created_at AS report_created_at
FROM amas.cases c
LEFT JOIN amas.reports r ON r.id = c.latest_report_id;
