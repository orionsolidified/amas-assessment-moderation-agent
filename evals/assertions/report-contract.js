const r = JSON.parse(output);
const dispositions = new Set([
  'ready_for_human_approval','minor_revision','major_revision',
  'insufficient_evidence','policy_conflict_requires_review','blocked_security'
]);
return Boolean(
  r && r.schema_version === '1.0' &&
  typeof r.case_id === 'string' &&
  dispositions.has(r.recommended_disposition) &&
  Array.isArray(r.findings) &&
  r.findings.every(f => f.code && f.category && f.severity && Array.isArray(f.evidence)) &&
  r.provenance && r.provenance.workflow_version && r.provenance.model_manifest
);
