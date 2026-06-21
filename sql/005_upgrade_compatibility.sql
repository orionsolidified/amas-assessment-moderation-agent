\set ON_ERROR_STOP on

-- Idempotent upgrade guards for installations created from an earlier draft.
-- This file also runs during a clean Docker initialisation, so every operation
-- must safely no-op when 001_schema.sql has already created the object.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE amas.findings ADD COLUMN IF NOT EXISTS report_id UUID;
ALTER TABLE amas.reports ADD COLUMN IF NOT EXISTS storage_bucket TEXT;
ALTER TABLE amas.reports ADD COLUMN IF NOT EXISTS storage_key TEXT;
ALTER TABLE amas.cases ADD COLUMN IF NOT EXISTS input_sha256 TEXT;
UPDATE amas.cases
SET input_sha256 = encode(digest(input_snapshot::text, 'sha256'), 'hex')
WHERE input_sha256 IS NULL;
ALTER TABLE amas.cases ALTER COLUMN input_sha256 SET NOT NULL;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'amas.findings'::regclass AND conname = 'findings_report_fk'
  ) THEN
    ALTER TABLE amas.findings
      ADD CONSTRAINT findings_report_fk
      FOREIGN KEY (report_id) REFERENCES amas.reports(id) ON DELETE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS findings_report_idx ON amas.findings(report_id);

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'amas.reports'::regclass AND conname = 'reports_id_case_unique'
  ) AND to_regclass('amas.reports_id_case_unique') IS NULL THEN
    ALTER TABLE amas.reports
      ADD CONSTRAINT reports_id_case_unique UNIQUE (id, case_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'amas.findings'::regclass AND conname = 'findings_id_report_case_unique'
  ) AND to_regclass('amas.findings_id_report_case_unique') IS NULL THEN
    ALTER TABLE amas.findings
      ADD CONSTRAINT findings_id_report_case_unique UNIQUE (id, report_id, case_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'amas.review_actions'::regclass AND conname = 'review_actions_report_case_fk'
  ) THEN
    ALTER TABLE amas.review_actions
      ADD CONSTRAINT review_actions_report_case_fk
      FOREIGN KEY (report_id, case_id) REFERENCES amas.reports(id, case_id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'amas.review_actions'::regclass AND conname = 'review_actions_finding_scope_fk'
  ) THEN
    ALTER TABLE amas.review_actions
      ADD CONSTRAINT review_actions_finding_scope_fk
      FOREIGN KEY (finding_id, report_id, case_id)
      REFERENCES amas.findings(id, report_id, case_id)
      ON DELETE SET NULL (finding_id);
  END IF;
END $$;
