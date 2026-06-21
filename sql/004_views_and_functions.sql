\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION amas.next_report_version(p_case_id UUID)
RETURNS INTEGER LANGUAGE sql VOLATILE AS $$
  SELECT COALESCE(MAX(report_version), 0) + 1 FROM amas.reports WHERE case_id = p_case_id;
$$;


CREATE OR REPLACE FUNCTION amas.enforce_immutable_input(p_existing TEXT, p_incoming TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
  IF p_existing IS DISTINCT FROM p_incoming THEN
    RAISE EXCEPTION 'case_id already exists with different submitted content; create a new case_id for a revised assessment'
      USING ERRCODE = '22000';
  END IF;
  RETURN p_existing;
END $$;

CREATE OR REPLACE FUNCTION amas.case_bundle(p_case_id UUID)
RETURNS JSONB LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
  'case', to_jsonb(c),
  'artifacts', COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.created_at) FROM amas.artifacts a WHERE a.case_id = c.id), '[]'::jsonb),
  'learning_outcomes', COALESCE((SELECT jsonb_agg(to_jsonb(lo) ORDER BY lo.outcome_code) FROM amas.learning_outcomes lo WHERE lo.case_id = c.id), '[]'::jsonb),
  'latest_preflight', (SELECT jsonb_build_object('facts', p.facts, 'findings', p.findings, 'workflow_version', p.workflow_version) FROM amas.preflight_runs p WHERE p.case_id = c.id ORDER BY p.started_at DESC LIMIT 1),
  'latest_report', (SELECT r.report FROM amas.reports r WHERE r.id = c.latest_report_id)
)
FROM amas.cases c WHERE c.id = p_case_id;
$$;

CREATE OR REPLACE FUNCTION amas.append_audit(
  p_case_id UUID,
  p_actor_type TEXT,
  p_actor_id TEXT,
  p_action TEXT,
  p_object_type TEXT,
  p_object_id TEXT,
  p_details JSONB,
  p_correlation_id TEXT,
  p_n8n_execution_id TEXT
) RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE v_id BIGINT;
BEGIN
  INSERT INTO amas.audit_events(tenant_id, case_id, actor_type, actor_id, action, object_type, object_id, details, correlation_id, n8n_execution_id)
  VALUES (COALESCE((SELECT tenant_id FROM amas.cases WHERE id=p_case_id),'default'), p_case_id, p_actor_type, p_actor_id, p_action, p_object_type, p_object_id, COALESCE(p_details,'{}'::jsonb), p_correlation_id, p_n8n_execution_id)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;
