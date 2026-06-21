#!/usr/bin/env python3
"""Generate importable n8n workflow JSON for AMAS.

The generated workflows intentionally use only core n8n nodes and named credentials.
After import, bind the placeholder credentials documented in docs/CONFIGURATION.md.
"""
from __future__ import annotations

import json
import textwrap
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "workflows"
OUT.mkdir(parents=True, exist_ok=True)
NS = uuid.UUID("aa7a06f6-65a8-48da-bd2d-4d1ca13ee51d")

PG_CREDENTIAL = {"postgres": {"id": "amas-postgresql-placeholder", "name": "AMAS PostgreSQL"}}
LLM_CREDENTIAL = {"httpHeaderAuth": {"id": "amas-llm-api-placeholder", "name": "AMAS LLM API"}}
ANYTHINGLLM_CREDENTIAL = {"httpHeaderAuth": {"id": "amas-anythingllm-api-placeholder", "name": "AMAS AnythingLLM API"}}


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, ":".join(parts)))


def clean(value: str) -> str:
    return textwrap.dedent(value).strip()


def node(wf: str, name: str, node_type: str, type_version: float | int, parameters: dict[str, Any], position: tuple[int, int], *, credentials: dict[str, Any] | None = None, on_error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "parameters": parameters,
        "id": uid(wf, name),
        "name": name,
        "type": node_type,
        "typeVersion": type_version,
        "position": list(position),
    }
    if credentials:
        result["credentials"] = credentials
    if on_error:
        result["onError"] = on_error
    return result


def webhook(wf: str, name: str, method: str, path: str, position=(0, 0)) -> dict[str, Any]:
    return node(wf, name, "n8n-nodes-base.webhook", 2.1, {
        "httpMethod": method,
        "path": path,
        "responseMode": "responseNode",
        "options": {},
    }, position)


def code(wf: str, name: str, js: str, position: tuple[int, int]) -> dict[str, Any]:
    return node(wf, name, "n8n-nodes-base.code", 2, {"jsCode": clean(js)}, position)


def postgres(wf: str, name: str, query: str, replacements: str, position: tuple[int, int]) -> dict[str, Any]:
    return node(wf, name, "n8n-nodes-base.postgres", 2.6, {
        "operation": "executeQuery",
        "query": clean(query),
        "options": {"queryReplacement": replacements},
    }, position, credentials=PG_CREDENTIAL)


def http(wf: str, name: str, url: str, body: str, position: tuple[int, int], *, headers: list[dict[str, str]] | None = None, credentials: dict[str, Any] | None = None, timeout: int = 300000, on_error: str | None = None, method: str = "POST") -> dict[str, Any]:
    params: dict[str, Any] = {
        "method": method,
        "url": url,
        "sendBody": method not in {"GET", "HEAD"},
        "contentType": "raw" if method not in {"GET", "HEAD"} else None,
        "rawContentType": "application/json" if method not in {"GET", "HEAD"} else None,
        "body": body if method not in {"GET", "HEAD"} else None,
        "options": {"timeout": timeout},
    }
    params = {k: v for k, v in params.items() if v is not None}
    if headers:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": headers}
    if credentials:
        params["authentication"] = "genericCredentialType"
        params["genericAuthType"] = "httpHeaderAuth"
    return node(wf, name, "n8n-nodes-base.httpRequest", 4.2, params, position, credentials=credentials, on_error=on_error)


def respond(wf: str, name: str, body_expr: str, position: tuple[int, int], status_expr: str | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if status_expr:
        options["responseCode"] = status_expr
    return node(wf, name, "n8n-nodes-base.respondToWebhook", 1.4, {
        "respondWith": "json",
        "responseBody": body_expr,
        "options": options,
    }, position)


def connect(connections: dict[str, Any], source: str, target: str, source_output: int = 0, target_input: int = 0) -> None:
    entry = connections.setdefault(source, {"main": []})["main"]
    while len(entry) <= source_output:
        entry.append([])
    entry[source_output].append({"node": target, "type": "main", "index": target_input})


def workflow(key: str, name: str, nodes: list[dict[str, Any]], connections: dict[str, Any], *, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": settings or {"executionOrder": "v1", "saveManualExecutions": True},
        "versionId": uid(key, "version"),
        "meta": {"templateCredsSetupCompleted": False},
        "tags": [],
    }


def write(filename: str, wf: dict[str, Any]) -> None:
    (OUT / filename).write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


PUBLIC_AUTH_PREFIX = r"""
const headers = $json.headers || {};
const received = String(headers['x-amas-api-token'] || headers['X-AMAS-API-Token'] || '');
const expected = String($env.AMAS_API_TOKEN || '');
if (!expected) throw new Error('AMAS_API_TOKEN is not configured');
if (received.length !== expected.length) throw new Error('Unauthorized');
let diff = 0;
for (let i = 0; i < expected.length; i++) diff |= received.charCodeAt(i) ^ expected.charCodeAt(i);
if (diff !== 0) throw new Error('Unauthorized');
const body = $json.body ?? $json;
"""
PUBLIC_AUTH_JS = PUBLIC_AUTH_PREFIX + "\nreturn [{ json: body }];"

INTERNAL_AUTH_PREFIX = r"""
const headers = $json.headers || {};
const auth = String(headers.authorization || headers.Authorization || '');
const bearer = auth.replace(/^Bearer\s+/i, '');
const received = String(headers['x-amas-internal-token'] || bearer || '');
const expected = String($env.AMAS_INTERNAL_TOKEN || '');
if (!expected) throw new Error('AMAS_INTERNAL_TOKEN is not configured');
if (received.length !== expected.length) throw new Error('Unauthorized');
let diff = 0;
for (let i = 0; i < expected.length; i++) diff |= received.charCodeAt(i) ^ expected.charCodeAt(i);
if (diff !== 0) throw new Error('Unauthorized');
const body = $json.body ?? $json;
"""
INTERNAL_AUTH_JS = INTERNAL_AUTH_PREFIX + "\nreturn [{ json: body }];"

EVAL_AUTH_PREFIX = r"""
const headers = $json.headers || {};
const auth = String(headers.authorization || headers.Authorization || '');
const bearer = auth.replace(/^Bearer\s+/i, '');
const received = String(headers['x-amas-eval-token'] || bearer || '');
const expected = String($env.AMAS_EVAL_TOKEN || '');
if (!expected) throw new Error('AMAS_EVAL_TOKEN is not configured');
if (received.length !== expected.length) throw new Error('Unauthorized');
let diff = 0;
for (let i = 0; i < expected.length; i++) diff |= received.charCodeAt(i) ^ expected.charCodeAt(i);
if (diff !== 0) throw new Error('Unauthorized');
const body = $json.body ?? $json;
"""
EVAL_AUTH_JS = EVAL_AUTH_PREFIX + "\nreturn [{ json: body }];"


def health_workflow() -> None:
    key = "00-health"
    nodes = [
        webhook(key, "Health Webhook", "GET", "amas/health", (0, 0)),
        code(key, "Build Health Response", r"""
            return [{json: {
              status: 'ok',
              service: 'AMAS n8n orchestration',
              workflow_version: $env.AMAS_WORKFLOW_VERSION || 'unknown',
              corpus_version: $env.AMAS_CORPUS_VERSION || 'unknown',
              execution_id: $execution.id,
              time: new Date().toISOString()
            }}];
        """, (240, 0)),
        respond(key, "Respond", "={{ $json }}", (480, 0)),
    ]
    c: dict[str, Any] = {}
    connect(c, "Health Webhook", "Build Health Response")
    connect(c, "Build Health Response", "Respond")
    write("00_health.json", workflow(key, "AMAS 00 - Health", nodes, c))


def intake_workflow() -> None:
    key = "01-case-intake"
    validate_js = PUBLIC_AUTH_PREFIX + r"""
const allowedArtifacts = new Set(['assessment_brief','rubric','module_descriptor','programme_specification','policy','supporting_document']);
const required = ['case_id','title','module_code','assessment_type','learning_outcomes','artifacts'];
for (const field of required) {
  if (body[field] === undefined || body[field] === null || body[field] === '') throw new Error(`Missing required field: ${field}`);
}
if (!/^[0-9a-fA-F-]{36}$/.test(String(body.case_id))) throw new Error('case_id must be a UUID');
if (!Array.isArray(body.learning_outcomes) || body.learning_outcomes.length === 0) throw new Error('At least one learning outcome is required');
if (!Array.isArray(body.artifacts) || body.artifacts.length < 2) throw new Error('Assessment brief and rubric are required');
const types = new Set(body.artifacts.map(a => a.artifact_type));
for (const t of types) if (!allowedArtifacts.has(t)) throw new Error(`Unsupported artifact_type: ${t}`);
if (!types.has('assessment_brief') || !types.has('rubric')) throw new Error('assessment_brief and rubric artifacts are required');
for (const a of body.artifacts) {
  if (typeof a.extracted_text !== 'string') throw new Error(`Artifact ${a.artifact_type} has no extracted_text`);
  if (a.extracted_text.length > 2000000) throw new Error(`Artifact ${a.artifact_type} exceeds extracted-text limit`);
}
body.tenant_id = body.tenant_id || 'default';
body.declared_ai_mode = body.declared_ai_mode || 'unspecified';
body.evaluation_mode = Boolean(body.evaluation_mode);
body.metadata = body.metadata || {};
body.idempotency_key = body.idempotency_key || body.case_id;
return [{json: body}];
"""
    upsert_sql = r"""
WITH p AS (SELECT $1::jsonb AS j),
case_upsert AS (
  INSERT INTO amas.cases AS existing (
    id, external_ref, tenant_id, title, module_code, module_title, study_level,
    credit_value, assessment_weight, assessment_type, individual_or_group,
    formative_or_summative, issue_date, submission_date, submitter_id,
    moderator_id, declared_ai_mode, evaluation_mode, status, metadata,
    input_snapshot, input_sha256, idempotency_key
  )
  SELECT
    (j->>'case_id')::uuid, NULLIF(j->>'external_ref',''), COALESCE(NULLIF(j->>'tenant_id',''),'default'),
    j->>'title', j->>'module_code', NULLIF(j->>'module_title',''), NULLIF(j->>'study_level',''),
    NULLIF(j->>'credit_value','')::numeric, NULLIF(j->>'assessment_weight','')::numeric,
    j->>'assessment_type', NULLIF(j->>'individual_or_group',''), NULLIF(j->>'formative_or_summative',''),
    NULLIF(j->>'issue_date','')::date, NULLIF(j->>'submission_date','')::date,
    NULLIF(j->>'submitter_id',''), NULLIF(j->>'moderator_id',''), NULLIF(j->>'declared_ai_mode',''),
    COALESCE((j->>'evaluation_mode')::boolean,false), 'normalised', COALESCE(j->'metadata','{}'::jsonb),
    j - 'artifacts' - 'learning_outcomes', encode(digest(j::text,'sha256'),'hex'), NULLIF(j->>'idempotency_key','')
  FROM p
  ON CONFLICT (id) DO UPDATE SET
    external_ref=EXCLUDED.external_ref, title=EXCLUDED.title, module_code=EXCLUDED.module_code,
    module_title=EXCLUDED.module_title, study_level=EXCLUDED.study_level,
    credit_value=EXCLUDED.credit_value, assessment_weight=EXCLUDED.assessment_weight,
    assessment_type=EXCLUDED.assessment_type, individual_or_group=EXCLUDED.individual_or_group,
    formative_or_summative=EXCLUDED.formative_or_summative, issue_date=EXCLUDED.issue_date,
    submission_date=EXCLUDED.submission_date, submitter_id=EXCLUDED.submitter_id,
    moderator_id=EXCLUDED.moderator_id, declared_ai_mode=EXCLUDED.declared_ai_mode,
    evaluation_mode=EXCLUDED.evaluation_mode, status='normalised', metadata=EXCLUDED.metadata,
    input_snapshot=EXCLUDED.input_snapshot,
    input_sha256=amas.enforce_immutable_input(existing.input_sha256,EXCLUDED.input_sha256)
  RETURNING id
),
artifact_upsert AS (
  INSERT INTO amas.artifacts (
    case_id, artifact_type, original_filename, mime_type, size_bytes, storage_bucket,
    storage_key, sha256, extracted_text, text_sha256, extraction_status, metadata
  )
  SELECT c.id, (a->>'artifact_type')::amas.artifact_type, NULLIF(a->>'original_filename',''),
    NULLIF(a->>'mime_type',''), NULLIF(a->>'size_bytes','')::bigint, NULLIF(a->>'storage_bucket',''),
    NULLIF(a->>'storage_key',''), NULLIF(a->>'sha256',''), COALESCE(a->>'extracted_text',''),
    NULLIF(a->>'text_sha256',''), COALESCE(NULLIF(a->>'extraction_status',''),'provided'),
    COALESCE(a->'metadata','{}'::jsonb)
  FROM p CROSS JOIN case_upsert c CROSS JOIN LATERAL jsonb_array_elements(p.j->'artifacts') a
  ON CONFLICT (case_id, artifact_type, sha256) DO UPDATE SET
    storage_bucket=EXCLUDED.storage_bucket, storage_key=EXCLUDED.storage_key,
    extracted_text=EXCLUDED.extracted_text, text_sha256=EXCLUDED.text_sha256,
    extraction_status=EXCLUDED.extraction_status, metadata=EXCLUDED.metadata
  RETURNING id
),
lo_upsert AS (
  INSERT INTO amas.learning_outcomes (case_id, outcome_code, description, level_descriptor, metadata)
  SELECT c.id, lo->>'outcome_code', lo->>'description', NULLIF(lo->>'level_descriptor',''),
    COALESCE(lo->'metadata','{}'::jsonb)
  FROM p CROSS JOIN case_upsert c CROSS JOIN LATERAL jsonb_array_elements(p.j->'learning_outcomes') lo
  ON CONFLICT (case_id, outcome_code) DO UPDATE SET
    description=EXCLUDED.description, level_descriptor=EXCLUDED.level_descriptor, metadata=EXCLUDED.metadata
  RETURNING id
),
audit AS (
  SELECT amas.append_audit(c.id,'user',NULLIF(p.j->>'submitter_id',''),'case_received','case',c.id::text,
    jsonb_build_object('evaluation_mode',COALESCE((p.j->>'evaluation_mode')::boolean,false)),
    NULLIF(p.j->>'idempotency_key',''),$2)
  FROM p CROSS JOIN case_upsert c
)
SELECT c.id::text AS case_id, amas.case_bundle(c.id) AS case_bundle
FROM case_upsert c;
"""
    nodes = [
        webhook(key, "Case Intake Webhook", "POST", "amas/v1/cases", (0, 0)),
        code(key, "Authenticate and Validate", validate_js, (220, 0)),
        postgres(key, "Persist Case", upsert_sql, "={{ [JSON.stringify($json), $execution.id] }}", (470, 0)),
        http(key, "Run Moderation Orchestrator", "={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/orchestrate' }}", "={{ JSON.stringify({case_id: $json.case_id}) }}", (730, 0), headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}], timeout=600000),
        respond(key, "Respond", "={{ $json }}", (990, 0)),
    ]
    c: dict[str, Any] = {}
    for a,b in [("Case Intake Webhook","Authenticate and Validate"),("Authenticate and Validate","Persist Case"),("Persist Case","Run Moderation Orchestrator"),("Run Moderation Orchestrator","Respond")]: connect(c,a,b)
    write("01_case_intake.json", workflow(key, "AMAS 01 - Case Intake", nodes, c))


def preflight_workflow() -> None:
    key = "02-preflight"
    preflight_js = r"""
const bundle = $json.case_bundle;
if (!bundle || !bundle.case) throw new Error('Case not found');
const c = bundle.case;
const artifacts = bundle.artifacts || [];
const los = bundle.learning_outcomes || [];
const byType = Object.fromEntries(artifacts.map(a => [a.artifact_type, a]));
const brief = String(byType.assessment_brief?.extracted_text || '');
const rubric = String(byType.rubric?.extracted_text || '');
const moduleDescriptor = String(byType.module_descriptor?.extracted_text || '');
const allText = [brief, rubric, moduleDescriptor, ...artifacts.filter(a => !['assessment_brief','rubric','module_descriptor'].includes(a.artifact_type)).map(a => a.extracted_text || '')].join('\n');
const findings = [];
const facts = {
  artifact_count: artifacts.length,
  learning_outcome_count: los.length,
  extraction_errors: [],
  mark_candidates: [],
  rubric_total: null,
  referenced_learning_outcomes: [],
  missing_learning_outcomes: [],
  injection_indicators: [],
  possible_personal_data: []
};
function add(code, category, severity, observation, recommendation, evidence = [], confidence = 1) {
  findings.push({finding_ref:`PREFLIGHT-${String(findings.length+1).padStart(3,'0')}`,code,category,severity,observation,interpretation:null,recommendation,confidence,human_judgment_required:true,evidence,metadata:{deterministic:true},verification_status:'verified'});
}
for (const a of artifacts) {
  if (String(a.extraction_status || '').startsWith('extraction_error') || a.extraction_status === 'ocr_required') {
    facts.extraction_errors.push({artifact_type:a.artifact_type,status:a.extraction_status});
    add('ARTIFACT_TEXT_UNAVAILABLE','document_integrity','major',`${a.artifact_type} text is unavailable (${a.extraction_status}).`,'Provide a machine-readable version or complete controlled OCR before moderation.',[{source_type:a.artifact_type,source_id:`CASE-${a.artifact_type.toUpperCase()}`,locator:'whole document',excerpt:''}],1);
  }
}
if (!brief.trim()) add('ASSESSMENT_BRIEF_MISSING','document_integrity','critical','The assessment brief has no extractable text.','Provide the assessment brief before moderation.',[],1);
if (!rubric.trim()) add('RUBRIC_MISSING','document_integrity','critical','The rubric has no extractable text.','Provide the rubric before moderation.',[],1);
if (!los.length) add('LEARNING_OUTCOMES_MISSING','outcome_alignment','critical','No learning outcomes were supplied.','Provide the approved module learning outcomes.',[],1);
if (c.issue_date && c.submission_date && new Date(c.submission_date) <= new Date(c.issue_date)) {
  add('INVALID_DATE_SEQUENCE','administrative_integrity','critical',`Submission date ${c.submission_date} is not after issue date ${c.issue_date}.`,'Correct the assessment dates.',[{source_type:'preflight',source_id:'PREFLIGHT',locator:'case metadata',excerpt:`issue_date=${c.issue_date}; submission_date=${c.submission_date}`}],1);
}
const markLine = /^.{0,220}?(\d+(?:\.\d+)?)\s*(?:marks?|points?|%)\s*$/gim;
let m;
while ((m = markLine.exec(rubric)) !== null) {
  const value = Number(m[1]);
  if (value >= 0 && value <= 100) facts.mark_candidates.push({line:m[0].trim(),value});
}
if (facts.mark_candidates.length >= 2) {
  const total = Math.round(facts.mark_candidates.reduce((s,x)=>s+x.value,0)*100)/100;
  facts.rubric_total = total;
  if (Math.abs(total-100) > 0.01) add('RUBRIC_TOTAL_INVALID','rubric_quality','critical',`Extracted rubric allocations total ${total}, not 100.`,'Correct and independently verify the rubric arithmetic.',[{source_type:'rubric',source_id:'CASE-RUBRIC',locator:'criterion mark allocations',excerpt:facts.mark_candidates.map(x=>x.line).slice(0,12).join(' | ')}],0.99);
}
const weightMatches = [...brief.matchAll(/(?:weight(?:ing)?|worth)\s*[:=-]?\s*(\d+(?:\.\d+)?)\s*%/gi)].map(x=>Number(x[1]));
if (c.assessment_weight != null && weightMatches.length && !weightMatches.some(v=>Math.abs(v-Number(c.assessment_weight))<0.01)) {
  add('ASSESSMENT_WEIGHT_CONFLICT','administrative_integrity','major',`Case metadata states ${c.assessment_weight}% but the brief contains ${[...new Set(weightMatches)].join(', ')}%.`,'Reconcile the approved module weighting and the published brief.',[{source_type:'assessment_brief',source_id:'CASE-ASSESSMENT_BRIEF',locator:'weighting statement',excerpt:brief.match(/.{0,80}(?:weight(?:ing)?|worth).{0,80}/i)?.[0] || ''}],0.98);
}
for (const lo of los) {
  const code = String(lo.outcome_code || '').trim();
  if (!code) continue;
  const pattern = new RegExp(`\\b${code.replace(/[.*+?^${}()|[\\]\\]/g,'\\$&')}\\b`,'i');
  if (pattern.test(brief + '\n' + rubric)) facts.referenced_learning_outcomes.push(code);
  else facts.missing_learning_outcomes.push(code);
}
if (facts.missing_learning_outcomes.length) add('OUTCOME_REFERENCES_ABSENT','outcome_alignment','major',`No explicit reference was found for: ${facts.missing_learning_outcomes.join(', ')}.`,'Verify that every assessed outcome is intentionally elicited and represented in the rubric.',los.filter(lo=>facts.missing_learning_outcomes.includes(lo.outcome_code)).map(lo=>({source_type:'learning_outcome',source_id:lo.outcome_code,locator:'declared outcome',excerpt:lo.description})),0.9);
const injectionPatterns = [
  /ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?/ig,
  /system\s+prompt/ig,
  /reveal\s+(?:your|the)\s+(?:instructions?|secrets?|tools?)/ig,
  /(?:call|invoke|use)\s+(?:the\s+)?(?:tool|function|api)/ig,
  /send\s+(?:the\s+)?(?:data|student|report).{0,80}(?:email|address|webhook)/ig
];
for (const re of injectionPatterns) for (const hit of allText.matchAll(re)) facts.injection_indicators.push(hit[0]);
if (facts.injection_indicators.length) add('SUSPECTED_PROMPT_INJECTION','security','critical',`Uploaded content contains ${facts.injection_indicators.length} instruction-like pattern(s) directed at an AI system.`,'Treat embedded instructions as untrusted data; inspect the source and do not grant action permissions.',[{source_type:'other',source_id:'CASE-UPLOADS',locator:'embedded text',excerpt:[...new Set(facts.injection_indicators)].slice(0,8).join(' | ')}],0.99);
const emails = [...allText.matchAll(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi)].map(x=>x[0]);
const studentIds = [...allText.matchAll(/\b(?:student\s*(?:id|no)|registration\s*(?:id|no))\s*[:#-]?\s*[A-Z0-9/-]{4,20}\b/gi)].map(x=>x[0]);
facts.possible_personal_data = [...new Set([...emails,...studentIds])].slice(0,30);
if (facts.possible_personal_data.length) add('POSSIBLE_PERSONAL_DATA','privacy','major',`The submitted package may contain personal identifiers (${facts.possible_personal_data.length} detected).`,'Remove or pseudonymise personal data unless an approved processing basis and protected model environment exist.',[{source_type:'other',source_id:'CASE-UPLOADS',locator:'detected identifiers',excerpt:facts.possible_personal_data.join(' | ')}],0.85);
return [{json:{case_id:c.id,case_bundle:bundle,facts,findings,status:'completed',workflow_version:$env.AMAS_WORKFLOW_VERSION || 'unknown',n8n_execution_id:$execution.id}}];
"""
    store_sql = r"""
WITH ins AS (
  INSERT INTO amas.preflight_runs(case_id,workflow_version,status,facts,findings,completed_at,n8n_execution_id)
  VALUES($1::uuid,$2,'completed',$3::jsonb,$4::jsonb,now(),$5)
  RETURNING id
), upd AS (
  UPDATE amas.cases SET status='preflight' WHERE id=$1::uuid RETURNING id
), audit AS (
  SELECT amas.append_audit($1::uuid,'system','preflight','preflight_completed','preflight_run',ins.id::text,
    jsonb_build_object('finding_count',jsonb_array_length($4::jsonb)),NULL,$5) FROM ins
)
SELECT jsonb_build_object('case_id',$1,'facts',$3::jsonb,'findings',$4::jsonb,'workflow_version',$2,'preflight_run_id',ins.id::text) AS output FROM ins;
"""
    nodes = [
        webhook(key,"Preflight Webhook","POST","amas/internal/preflight",(0,0)),
        code(key,"Authenticate",INTERNAL_AUTH_JS,(210,0)),
        postgres(key,"Load Case Bundle","SELECT amas.case_bundle($1::uuid) AS case_bundle;","={{ [$json.case_id] }}",(430,0)),
        code(key,"Run Deterministic Checks",preflight_js,(650,0)),
        postgres(key,"Store Preflight",store_sql,"={{ [$json.case_id,$json.workflow_version,JSON.stringify($json.facts),JSON.stringify($json.findings),$execution.id] }}",(900,0)),
        respond(key,"Respond","={{ $json.output }}",(1140,0)),
    ]
    c: dict[str,Any]={}
    for a,b in [("Preflight Webhook","Authenticate"),("Authenticate","Load Case Bundle"),("Load Case Bundle","Run Deterministic Checks"),("Run Deterministic Checks","Store Preflight"),("Store Preflight","Respond")]: connect(c,a,b)
    write("02_deterministic_preflight.json",workflow(key,"AMAS 02 - Deterministic Preflight",nodes,c))


def retrieval_workflow() -> None:
    key="03-policy-retrieval"
    build_js = INTERNAL_AUTH_PREFIX + r"""
const caseId = body.case_id;
const bundle = body.case_bundle || {};
const c = bundle.case || {};
const defaultQueries = [
  `assessment moderation requirements ${c.assessment_type || ''}`,
  `learning outcome alignment rubric assessment level ${c.study_level || ''}`,
  `generative AI permitted prohibited disclosure assessment`,
  `group assessment individual contribution moderation`,
  `assessment accessibility equity reasonable adjustment`
];
const queries = Array.isArray(body.queries) && body.queries.length ? body.queries : defaultQueries;
return queries.slice(0,10).map((q,index)=>({json:{case_id:caseId,case_bundle:bundle,query:String(q),query_index:index,top_n:Number(body.top_n||8),score_threshold:Number(body.score_threshold||0.2)}}));
"""
    normalize_js = r"""
const responses = $input.all();
const requests = $('Build Retrieval Queries').all().map(i=>i.json);
const chunks = [];
const records = [];
for (let i=0;i<responses.length;i++) {
  const req = requests[i] || {};
  const raw = responses[i]?.json || {};
  const list = Array.isArray(raw.result) ? raw.result : Array.isArray(raw.results) ? raw.results : Array.isArray(raw.documents) ? raw.documents : [];
  const accepted=[];
  for (const hit of list) {
    const md = typeof hit.metadata === 'string' ? (()=>{try{return JSON.parse(hit.metadata)}catch{return {}}})() : (hit.metadata || {});
    const score = Number(hit.score ?? (hit.distance != null ? 1-Number(hit.distance) : 0));
    const sourceId = String(md.source_id || md.sourceId || md.title || md.sourceDocument || hit.source_id || hit.id || 'UNKNOWN');
    const chunkId = String(hit.chunk_id || hit.id || md.id || `${sourceId}-${accepted.length+1}`);
    const item={source_type:'policy',source_id:sourceId,chunk_id:chunkId,locator:String(md.locator || md.section || md.title || 'retrieved passage'),excerpt:String(hit.text || hit.content || '').slice(0,6000),score,authority_rank:Number(md.authority_rank || 0),version:String(md.version || ''),status:String(md.status || 'active'),metadata:md};
    if (score >= Number(req.score_threshold || 0.2)) {accepted.push(item); chunks.push(item);}
  }
  records.push({query:req.query,request:{topN:req.top_n,scoreThreshold:req.score_threshold},response:raw,accepted_chunks:accepted});
}
const unique=[]; const seen=new Set();
for (const ch of chunks.sort((a,b)=>b.authority_rank-a.authority_rank || b.score-a.score)) {
  const k=`${ch.source_id}::${ch.chunk_id}`; if (!seen.has(k)) {seen.add(k); unique.push(ch);}
}
return [{json:{case_id:requests[0]?.case_id,case_bundle:requests[0]?.case_bundle,corpus_version:$env.AMAS_CORPUS_VERSION || null,workspace_slug:$env.ANYTHINGLLM_WORKSPACE_SLUG,policy_evidence:unique.slice(0,30),retrieval_records:records,n8n_execution_id:$execution.id}}];
"""
    registry_sql=r"""
WITH p AS (SELECT $1::jsonb AS j),
params AS (
  SELECT j, COALESCE(NULLIF(j#>>'{case_bundle,case,issue_date}','')::date,CURRENT_DATE) AS effective_on
  FROM p
),
candidates AS (
  SELECT ordinality, value AS chunk
  FROM params CROSS JOIN LATERAL jsonb_array_elements(COALESCE(j->'policy_evidence','[]'::jsonb)) WITH ORDINALITY
),
matched AS (
  SELECT c.ordinality,
    c.chunk || jsonb_build_object(
      'source_id',ps.source_id,
      'version',ps.version,
      'authority_rank',ps.authority_rank,
      'status',ps.status,
      'metadata',COALESCE(c.chunk->'metadata','{}'::jsonb) || jsonb_build_object(
        'registry_validated',true,
        'policy_source_record_id',ps.id::text,
        'authority_scope',ps.authority_scope,
        'effective_from',ps.effective_from,
        'effective_to',ps.effective_to,
        'sha256',ps.sha256
      )
    ) AS chunk
  FROM candidates c
  CROSS JOIN params pa
  CROSS JOIN LATERAL (
    SELECT src.*
    FROM amas.policy_sources src
    WHERE src.source_id=c.chunk->>'source_id'
      AND (NULLIF(c.chunk->>'version','') IS NULL OR src.version=c.chunk->>'version')
      AND src.status='active'
      AND (src.effective_from IS NULL OR src.effective_from<=pa.effective_on)
      AND (src.effective_to IS NULL OR src.effective_to>=pa.effective_on)
    ORDER BY CASE WHEN src.version=c.chunk->>'version' THEN 0 ELSE 1 END,
             src.authority_rank DESC, src.created_at DESC
    LIMIT 1
  ) ps
),
accepted AS (
  SELECT COALESCE(jsonb_agg(chunk ORDER BY ordinality),'[]'::jsonb) AS chunks FROM matched
),
rejected AS (
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'source_id',c.chunk->>'source_id',
    'chunk_id',c.chunk->>'chunk_id',
    'reason','source/version is not registered, active, and effective for this case'
  ) ORDER BY c.ordinality),'[]'::jsonb) AS chunks
  FROM candidates c
  WHERE NOT EXISTS (SELECT 1 FROM matched m WHERE m.ordinality=c.ordinality)
)
SELECT
  j->>'case_id' AS case_id,
  j->'case_bundle' AS case_bundle,
  j->>'corpus_version' AS corpus_version,
  j->>'workspace_slug' AS workspace_slug,
  accepted.chunks AS policy_evidence,
  rejected.chunks AS registry_rejected,
  j->'retrieval_records' AS retrieval_records,
  j->>'n8n_execution_id' AS n8n_execution_id
FROM params CROSS JOIN accepted CROSS JOIN rejected;
"""
    store_sql=r"""
INSERT INTO amas.retrieval_runs(case_id,query,corpus_version,workspace_slug,request,response,accepted_chunks,n8n_execution_id)
VALUES($1::uuid,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$8)
RETURNING jsonb_build_object('case_id',$1,'case_bundle',$9::jsonb,'corpus_version',$3,'workspace_slug',$4,'policy_evidence',$7::jsonb,'registry_rejected',$10::jsonb,'retrieval_run_id',id::text) AS output;
"""
    nodes=[
        webhook(key,"Policy Retrieval Webhook","POST","amas/internal/policy-retrieval",(0,0)),
        code(key,"Build Retrieval Queries",build_js,(240,0)),
        http(key,"AnythingLLM Vector Search","={{ $env.ANYTHINGLLM_BASE_URL.replace(/\\/$/, '') + '/api/v1/workspace/' + encodeURIComponent($env.ANYTHINGLLM_WORKSPACE_SLUG) + '/vector-search' }}","={{ JSON.stringify({query:$json.query,topN:$json.top_n,scoreThreshold:$json.score_threshold}) }}",(500,0),credentials=ANYTHINGLLM_CREDENTIAL,timeout=120000,on_error="continueRegularOutput"),
        code(key,"Normalize and Deduplicate",normalize_js,(750,0)),
        postgres(key,"Validate Policy Registry",registry_sql,"={{ [JSON.stringify($json)] }}",(980,0)),
        postgres(key,"Store Retrieval",""+store_sql,"={{ [$json.case_id,$json.retrieval_records.map(r=>r.query).join(' | '),$json.corpus_version,$json.workspace_slug,JSON.stringify($json.retrieval_records.map(r=>r.request)),JSON.stringify($json.retrieval_records.map(r=>r.response)),JSON.stringify($json.policy_evidence),$execution.id,JSON.stringify($json.case_bundle),JSON.stringify($json.registry_rejected || [])] }}",(1220,0)),
        respond(key,"Respond","={{ $json.output }}",(1460,0)),
    ]
    c:dict[str,Any]={}
    for a,b in [("Policy Retrieval Webhook","Build Retrieval Queries"),("Build Retrieval Queries","AnythingLLM Vector Search"),("AnythingLLM Vector Search","Normalize and Deduplicate"),("Normalize and Deduplicate","Validate Policy Registry"),("Validate Policy Registry","Store Retrieval"),("Store Retrieval","Respond")]: connect(c,a,b)
    write("03_policy_retrieval.json",workflow(key,"AMAS 03 - AnythingLLM Policy Retrieval",nodes,c))


def llm_workflow(filename: str, title: str, path: str, prompt_key: str, output_kind: str) -> None:
    key=f"llm-{prompt_key}"
    load_sql=r"""
SELECT id::text AS prompt_version_id,prompt_key,version,system_prompt,user_template,output_schema,model_config,content_sha256,$2::jsonb AS context
FROM amas.prompt_versions WHERE prompt_key=$1 AND active=TRUE LIMIT 1;
"""
    build_js=r"""
const ctx = $json.context || {};
const stringify = (v) => JSON.stringify(v ?? {}, null, 2);
const replacements = {
  '{{CASE_BUNDLE_JSON}}': stringify(ctx.case_bundle),
  '{{PREFLIGHT_JSON}}': stringify(ctx.preflight),
  '{{POLICY_JSON}}': stringify(ctx.policy_evidence || ctx.policy),
  '{{VERIFIED_FINDINGS_JSON}}': stringify(ctx.verified_findings || ctx.verification?.verified_findings),
  '{{REJECTED_FINDINGS_JSON}}': stringify(ctx.rejected_findings || ctx.verification?.rejected_findings),
  '{{CRITIC_JSON}}': stringify(ctx.critic),
  '{{PROVENANCE_JSON}}': stringify(ctx.provenance_seed)
};
let user = String($json.user_template || '');
for (const [token,value] of Object.entries(replacements)) user = user.split(token).join(value);
const system = `${$json.system_prompt}\n\nOUTPUT CONTRACT (JSON Schema):\n${stringify($json.output_schema)}\nReturn only the JSON object.`;
const cfg = $json.model_config || {};
const model = ctx.model || (ctx.use_critic_model ? $env.LLM_CRITIC_MODEL : $env.LLM_PRIMARY_MODEL);
return [{json:{context:ctx,prompt_version_id:$json.prompt_version_id,prompt_key:$json.prompt_key,prompt_version:$json.version,prompt_hash:$json.content_sha256,started_at_ms:Date.now(),llm_request:{model,messages:[{role:'system',content:system},{role:'user',content:user}],temperature:Number(cfg.temperature ?? 0),max_tokens:Number(cfg.max_tokens ?? 4500),response_format:{type:'json_object'}}}}];
"""
    parse_template=r"""
const built = $('Build LLM Request').item.json;
const raw = $json;
function contentOf(x) {
  if (typeof x === 'string') return x;
  if (typeof x?.choices?.[0]?.message?.content === 'string') return x.choices[0].message.content;
  if (Array.isArray(x?.choices?.[0]?.message?.content)) return x.choices[0].message.content.map(p=>p.text||p.content||'').join('');
  if (typeof x?.output_text === 'string') return x.output_text;
  if (Array.isArray(x?.output)) return x.output.map(o=>o.content||o.text||'').join('');
  if (x && typeof x === 'object' && x.error) throw new Error(`LLM request failed: ${JSON.stringify(x.error)}`);
  return JSON.stringify(x);
}
let text = contentOf(raw).trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');
const first=text.indexOf('{'), last=text.lastIndexOf('}');
if (first>=0 && last>first) text=text.slice(first,last+1);
let parsed;
try { parsed=JSON.parse(text); } catch (e) { throw new Error(`Model output was not valid JSON: ${e.message}; prefix=${text.slice(0,400)}`); }
const kind='__OUTPUT_KIND__';
if (kind==='specialist') {
  if (!Array.isArray(parsed.findings) || !Array.isArray(parsed.uncertainties)) throw new Error('Specialist output lacks findings or uncertainties arrays');
  parsed.specialist_key='__PROMPT_KEY__';
  parsed.summary=String(parsed.summary||'');
  parsed.applicable=parsed.applicable !== false;
  parsed.findings=parsed.findings.map((f,i)=>({
    finding_ref:String(f.finding_ref||`__PREFIX__-${String(i+1).padStart(3,'0')}`),
    code:String(f.code||'UNSPECIFIED_FINDING').toUpperCase().replace(/[^A-Z0-9_]/g,'_').slice(0,80),
    category:String(f.category||'other'),
    severity:['info','minor','major','critical'].includes(f.severity)?f.severity:'minor',
    observation:String(f.observation||''), interpretation:f.interpretation==null?null:String(f.interpretation),
    recommendation:String(f.recommendation||''), confidence:Math.max(0,Math.min(1,Number(f.confidence??0.5))),
    human_judgment_required:f.human_judgment_required!==false,
    evidence:Array.isArray(f.evidence)?f.evidence:[], metadata:f.metadata&&typeof f.metadata==='object'?f.metadata:{}
  }));
} else if (kind==='profiler') {
  if (!parsed.assessment_profile || !Array.isArray(parsed.optional_specialists)) throw new Error('Profiler output is invalid');
  parsed.optional_specialists=parsed.optional_specialists.filter(x=>['programming_assessment','group_work'].includes(x));
} else if (kind==='critic') {
  if (!Array.isArray(parsed.finding_reviews)) parsed.finding_reviews=[];
  if (!Array.isArray(parsed.missing_analyses)) parsed.missing_analyses=[];
  if (!Array.isArray(parsed.systemic_risks)) parsed.systemic_risks=[];
}
const usage=raw.usage||{};
return [{json:{case_id:built.context.case_id,context:built.context,output:parsed,raw_response:raw,prompt_version_id:built.prompt_version_id,prompt_key:built.prompt_key,prompt_version:built.prompt_version,prompt_hash:built.prompt_hash,model:built.llm_request.model,latency_ms:Date.now()-built.started_at_ms,input_tokens:Number(usage.prompt_tokens||usage.input_tokens||0),output_tokens:Number(usage.completion_tokens||usage.output_tokens||0),n8n_execution_id:$execution.id}}];
"""
    prefix=''.join(x[0] for x in prompt_key.split('_')).upper()
    parse_js=parse_template.replace('__OUTPUT_KIND__',output_kind).replace('__PROMPT_KEY__',prompt_key).replace('__PREFIX__',prefix)
    store_sql=r"""
WITH ins AS (
 INSERT INTO amas.agent_runs(case_id,specialist_key,prompt_version_id,model,model_provider,request_hash,request,response,parsed_output,status,latency_ms,input_tokens,output_tokens,n8n_execution_id,completed_at)
 VALUES($1::uuid,$2,$3::uuid,$4,$5,encode(digest($6::text,'sha256'),'hex'),$6::jsonb,$7::jsonb,$8::jsonb,'completed',$9,$10,$11,$12,now())
 RETURNING id
)
SELECT jsonb_build_object('case_id',$1,'agent_run_id',ins.id::text,'prompt_key',$2,'prompt_version',$13,'prompt_hash',$14,'model',$4,'output',$8::jsonb) AS result FROM ins;
"""
    response_js=r"""
const r=$json.result;
const original=$('Parse and Validate JSON').item.json;
const kind='__OUTPUT_KIND__';
if (kind==='specialist') return [{json:{case_id:r.case_id,specialist_key:r.prompt_key,agent_run_id:r.agent_run_id,prompt_version:r.prompt_version,prompt_hash:r.prompt_hash,model:r.model,output:r.output}}];
if (kind==='profiler') return [{json:{case_id:r.case_id,profiler:r.output,agent_run_id:r.agent_run_id,prompt_version:r.prompt_version,prompt_hash:r.prompt_hash,model:r.model}}];
if (kind==='critic') return [{json:{...original.context,critic:r.output,critic_run:{agent_run_id:r.agent_run_id,prompt_version:r.prompt_version,prompt_hash:r.prompt_hash,model:r.model}}}];
return [{json:r}];
""".replace('__OUTPUT_KIND__',output_kind)
    nodes=[
        webhook(key,"LLM Workflow Webhook","POST",path,(0,0)),
        code(key,"Authenticate",INTERNAL_AUTH_JS,(200,0)),
        postgres(key,"Load Active Prompt",load_sql,"={{ ['"+prompt_key+"',JSON.stringify($json)] }}",(420,0)),
        code(key,"Build LLM Request",build_js,(650,0)),
        http(key,"Call Model Gateway","={{ $env.LLM_BASE_URL.replace(/\\/$/, '') + '/chat/completions' }}","={{ JSON.stringify($json.llm_request) }}",(900,0),credentials=LLM_CREDENTIAL,timeout=300000),
        code(key,"Parse and Validate JSON",parse_js,(1140,0)),
        postgres(key,"Store Agent Run",store_sql,"={{ [$json.case_id,$json.prompt_key,$json.prompt_version_id,$json.model,$env.LLM_PROVIDER_NAME || 'openai-compatible',JSON.stringify($('Build LLM Request').item.json.llm_request),JSON.stringify($json.raw_response),JSON.stringify($json.output),$json.latency_ms,$json.input_tokens,$json.output_tokens,$execution.id,$json.prompt_version,$json.prompt_hash] }}",(1380,0)),
        code(key,"Shape Response",response_js,(1610,0)),
        respond(key,"Respond","={{ $json }}",(1830,0)),
    ]
    c:dict[str,Any]={}
    for a,b in [("LLM Workflow Webhook","Authenticate"),("Authenticate","Load Active Prompt"),("Load Active Prompt","Build LLM Request"),("Build LLM Request","Call Model Gateway"),("Call Model Gateway","Parse and Validate JSON"),("Parse and Validate JSON","Store Agent Run"),("Store Agent Run","Shape Response"),("Shape Response","Respond")]: connect(c,a,b)
    write(filename,workflow(key,title,nodes,c))


def evidence_workflow() -> None:
    key='21-evidence-verifier'
    verify_js=INTERNAL_AUTH_PREFIX+r"""
const bundle=body.case_bundle||{};
const artifacts=bundle.artifacts||[];
const los=bundle.learning_outcomes||[];
const preflight=body.preflight||{};
const policy=(body.policy_evidence?.policy_evidence||body.policy_evidence||body.policy||[]);
const specialistOutputs=body.specialist_outputs||[];
const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
const artifactMap=new Map();
for (const a of artifacts) {
  const base=`CASE-${String(a.artifact_type).toUpperCase()}`;
  if (a.source_id) artifactMap.set(String(a.source_id),a);
  if (['assessment_brief','rubric','module_descriptor','programme_specification'].includes(a.artifact_type)) artifactMap.set(base,a);
  artifactMap.set(String(a.id),a);
}
const loMap=new Map(los.map(lo=>[String(lo.outcome_code),lo]));
const policyMap=new Map(policy.map(p=>[`${p.source_id}::${p.chunk_id||''}`,p]));
const preflightCodes=new Set((preflight.findings||[]).map(f=>f.code));
const verified=[]; const rejected=[];
function evidenceValid(ev) {
  if (!ev||!ev.source_type||!ev.source_id) return {ok:false,reason:'missing evidence identity'};
  let sourceText='';
  if (ev.source_type==='policy') {
    const p=policyMap.get(`${ev.source_id}::${ev.chunk_id||''}`) || policy.find(x=>x.source_id===ev.source_id);
    if (!p) return {ok:false,reason:'policy source/chunk was not retrieved'};
    if (String(p.status||'active')!=='active') return {ok:false,reason:'policy source is not active'};
    if (p.metadata?.registry_validated!==true) return {ok:false,reason:'policy source was not validated against the PostgreSQL authority registry'};
    sourceText=p.excerpt||p.text||'';
  } else if (ev.source_type==='learning_outcome') {
    const lo=loMap.get(String(ev.source_id)); if (!lo) return {ok:false,reason:'learning outcome does not exist'};
    sourceText=lo.description||'';
  } else if (ev.source_type==='preflight') {
    if (ev.source_id!=='PREFLIGHT' && !preflightCodes.has(ev.source_id)) return {ok:false,reason:'preflight source does not exist'};
    return {ok:true,reason:'deterministic preflight evidence'};
  } else {
    const a=artifactMap.get(String(ev.source_id)); if (!a) return {ok:false,reason:'case artifact does not exist'};
    sourceText=a.extracted_text||'';
  }
  const excerpt=norm(ev.excerpt);
  if (!excerpt) return {ok:false,reason:'empty excerpt'};
  const source=norm(sourceText);
  const probe=excerpt.slice(0,Math.min(140,excerpt.length));
  if (!source.includes(probe)) {
    const words=probe.split(' ').filter(w=>w.length>4);
    const overlap=words.length?words.filter(w=>source.includes(w)).length/words.length:0;
    if (overlap<0.65) return {ok:false,reason:'excerpt is not supported by identified source'};
  }
  return {ok:true,reason:'matched source'};
}
for (const wrapper of specialistOutputs) {
  const out=wrapper.output||wrapper;
  for (const f0 of (out.findings||[])) {
    const f=JSON.parse(JSON.stringify(f0));
    const checks=(f.evidence||[]).map(evidenceValid);
    const validCount=checks.filter(x=>x.ok).length;
    const requiresPolicy=(f.category==='policy_compliance'||String(f.code).includes('POLICY'));
    const hasPolicy=(f.evidence||[]).some((e,i)=>e.source_type==='policy'&&checks[i]?.ok);
    const requiredCount=['major','critical'].includes(f.severity)?1:0;
    const ok=validCount>=requiredCount && (!requiresPolicy||hasPolicy);
    f.metadata={...(f.metadata||{}),evidence_checks:checks,origin_specialist:out.specialist_key||wrapper.specialist_key};
    f.verification_status=ok?'verified':'rejected';
    if (ok) verified.push(f); else rejected.push({...f,rejection_reason:checks.filter(x=>!x.ok).map(x=>x.reason).join('; ') || 'insufficient supporting evidence'});
  }
}
return [{json:{case_id:body.case_id,case_bundle:bundle,preflight,policy_evidence:body.policy_evidence,assessment_profile:body.assessment_profile,specialist_outputs:specialistOutputs,verified_findings:verified,rejected_findings:rejected,verification_summary:{verified:verified.length,rejected:rejected.length},provenance_seed:body.provenance_seed||{},use_critic_model:true}}];
"""
    nodes=[webhook(key,"Evidence Verifier Webhook","POST","amas/internal/evidence-verifier",(0,0)),code(key,"Verify Evidence",verify_js,(250,0)),respond(key,"Respond","={{ $json }}",(510,0))]
    c:dict[str,Any]={};connect(c,"Evidence Verifier Webhook","Verify Evidence");connect(c,"Verify Evidence","Respond")
    write("21_evidence_verifier.json",workflow(key,"AMAS 21 - Evidence and Citation Verifier",nodes,c))


def orchestrator_workflow() -> None:
    key='20-orchestrator'
    load_sql=r"""
WITH upd AS (UPDATE amas.cases SET status='analysing' WHERE id=$1::uuid RETURNING id)
SELECT $1::text AS case_id, amas.case_bundle($1::uuid) AS case_bundle FROM upd;
"""
    build_calls_js=r"""
const caseId=$('Load Case and Mark Analysing').first().json.case_id;
const bundle=$('Load Case and Mark Analysing').first().json.case_bundle;
const preflight=$('Run Preflight').first().json;
const policy=$('Retrieve Policy Evidence').first().json;
const profiler=$('Profile and Route').first().json.profiler||{};
const mandatory=['outcome_alignment','rubric_quality','assessment_validity','ai_use_design','policy_accessibility'];
const optional=Array.isArray(profiler.optional_specialists)?profiler.optional_specialists:[];
const selected=[...new Set([...mandatory,...optional])];
const pathMap={outcome_alignment:'outcome-alignment',rubric_quality:'rubric-quality',assessment_validity:'assessment-validity',ai_use_design:'ai-use-design',policy_accessibility:'policy-accessibility',programming_assessment:'programming-assessment',group_work:'group-work'};
const sourceBundle=JSON.parse(JSON.stringify(bundle));
const singletonTypes=new Set(['assessment_brief','rubric','module_descriptor','programme_specification']);
sourceBundle.artifacts=(sourceBundle.artifacts||[]).map(a=>{
  const base=`CASE-${String(a.artifact_type).toUpperCase()}`;
  const suffix=String(a.id||a.sha256||'').replace(/[^A-Za-z0-9]/g,'').slice(0,12).toUpperCase();
  return {...a,source_id:singletonTypes.has(a.artifact_type)?base:`${base}-${suffix||'UNKNOWN'}`};
});
const provenanceSeed={workflow_version:$env.AMAS_WORKFLOW_VERSION||'unknown',corpus_version:$env.AMAS_CORPUS_VERSION||null,n8n_execution_id:$execution.id,input_hashes:Object.fromEntries((bundle.artifacts||[]).map(a=>[a.artifact_type,a.sha256||a.text_sha256||null]))};
return selected.map(s=>({json:{case_id:caseId,specialist_key:s,url:`${$env.N8N_INTERNAL_BASE_URL.replace(/\/$/,'')}/webhook/amas/internal/specialist/${pathMap[s]}`,payload:{case_id:caseId,case_bundle:sourceBundle,preflight,policy_evidence:policy,assessment_profile:profiler.assessment_profile||{},provenance_seed:provenanceSeed}}}));
"""
    collect_js=r"""
const calls=$('Build Specialist Calls').all().map(i=>i.json);
const responses=$input.all();
const specialistOutputs=[];
for (let i=0;i<calls.length;i++) {
  const response=responses[i]?.json||{};
  if (response.error) specialistOutputs.push({case_id:calls[i].case_id,specialist_key:calls[i].specialist_key,error:response.error,output:{specialist_key:calls[i].specialist_key,applicable:true,summary:'Specialist execution failed',findings:[],uncertainties:[{question:'Specialist execution failed',impact:'Manual review is required',required_information:String(response.error.message||response.error)}],metrics:{}}});
  else specialistOutputs.push(response);
}
const first=calls[0]?.payload||{};
return [{json:{...first,specialist_outputs:specialistOutputs}}];
"""
    nodes=[
      webhook(key,"Orchestrator Webhook","POST","amas/internal/orchestrate",(0,0)),
      code(key,"Authenticate",INTERNAL_AUTH_JS,(190,0)),
      postgres(key,"Load Case and Mark Analysing",load_sql,"={{ [$json.case_id] }}",(410,0)),
      http(key,"Run Preflight","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/preflight' }}","={{ JSON.stringify({case_id:$json.case_id}) }}",(640,-160),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=180000),
      http(key,"Retrieve Policy Evidence","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/policy-retrieval' }}","={{ JSON.stringify({case_id:$('Load Case and Mark Analysing').first().json.case_id,case_bundle:$('Load Case and Mark Analysing').first().json.case_bundle}) }}",(880,-160),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=180000),
      http(key,"Profile and Route","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/profile' }}","={{ JSON.stringify({case_id:$('Load Case and Mark Analysing').first().json.case_id,case_bundle:$('Load Case and Mark Analysing').first().json.case_bundle,preflight:$('Run Preflight').first().json}) }}",(1120,-160),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=240000),
      code(key,"Build Specialist Calls",build_calls_js,(1360,0)),
      http(key,"Dispatch Selected Specialists","={{ $json.url }}","={{ JSON.stringify($json.payload) }}",(1600,0),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=300000,on_error="continueRegularOutput"),
      code(key,"Collect Specialist Outputs",collect_js,(1840,0)),
      http(key,"Verify Evidence","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/evidence-verifier' }}","={{ JSON.stringify($json) }}",(2080,0),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=180000),
      http(key,"Run Adversarial Critic","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/critic' }}","={{ JSON.stringify($json) }}",(2320,0),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=300000),
      http(key,"Synthesize and Store Report","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/internal/synthesize' }}","={{ JSON.stringify($json) }}",(2560,0),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=360000),
      respond(key,"Respond","={{ $json }}",(2800,0))
    ]
    c:dict[str,Any]={}
    for a,b in [("Orchestrator Webhook","Authenticate"),("Authenticate","Load Case and Mark Analysing"),("Load Case and Mark Analysing","Run Preflight"),("Run Preflight","Retrieve Policy Evidence"),("Retrieve Policy Evidence","Profile and Route"),("Profile and Route","Build Specialist Calls"),("Build Specialist Calls","Dispatch Selected Specialists"),("Dispatch Selected Specialists","Collect Specialist Outputs"),("Collect Specialist Outputs","Verify Evidence"),("Verify Evidence","Run Adversarial Critic"),("Run Adversarial Critic","Synthesize and Store Report"),("Synthesize and Store Report","Respond")]:connect(c,a,b)
    write("20_moderation_orchestrator.json",workflow(key,"AMAS 20 - Moderation Orchestrator",nodes,c))


def synthesis_workflow() -> None:
    key='23-synthesis'
    load_sql=r"""SELECT id::text AS prompt_version_id,prompt_key,version,system_prompt,user_template,output_schema,model_config,content_sha256,$2::jsonb AS context FROM amas.prompt_versions WHERE prompt_key=$1 AND active=TRUE LIMIT 1;"""
    build_js=r"""
const ctx=$json.context||{}; const S=v=>JSON.stringify(v??{},null,2);
let user=String($json.user_template||'');
const map={'{{CASE_BUNDLE_JSON}}':S(ctx.case_bundle),'{{PREFLIGHT_JSON}}':S(ctx.preflight),'{{POLICY_JSON}}':S(ctx.policy_evidence),'{{VERIFIED_FINDINGS_JSON}}':S(ctx.verified_findings),'{{CRITIC_JSON}}':S(ctx.critic),'{{PROVENANCE_JSON}}':S(ctx.provenance_seed)};
for(const [k,v] of Object.entries(map)) user=user.split(k).join(v);
const system=`${$json.system_prompt}\n\nOUTPUT CONTRACT:\n${S($json.output_schema)}\nReturn only JSON. The final workflow deterministically recalculates disposition and canonical findings.`;
const cfg=$json.model_config||{};
return [{json:{context:ctx,prompt_version_id:$json.prompt_version_id,prompt_version:$json.version,prompt_hash:$json.content_sha256,started_at_ms:Date.now(),llm_request:{model:$env.LLM_PRIMARY_MODEL,messages:[{role:'system',content:system},{role:'user',content:user}],temperature:Number(cfg.temperature??0),max_tokens:Number(cfg.max_tokens??7000),response_format:{type:'json_object'}}}}];
"""
    finalize_js=r"""
const built=$('Build Synthesis Request').item.json; const ctx=built.context; const raw=$json;
let text=typeof raw?.choices?.[0]?.message?.content==='string'?raw.choices[0].message.content:(raw.output_text||JSON.stringify(raw));
text=String(text).trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,''); const a=text.indexOf('{'),b=text.lastIndexOf('}'); if(a>=0&&b>a)text=text.slice(a,b+1);
let draft={}; try{draft=JSON.parse(text)}catch{draft={executive_summary:'The synthesis model returned invalid JSON; the deterministic report was assembled from verified findings.'}}
const preflightFindings=(ctx.preflight?.findings||[]).map(f=>({...f,verification_status:'verified'}));
let findings=[...preflightFindings,...(ctx.verified_findings||[])];
const reviews=new Map((ctx.critic?.finding_reviews||[]).map(r=>[r.finding_ref,r]));
findings=findings.flatMap(f=>{const r=reviews.get(f.finding_ref); if(!r)return[f]; if(r.action==='reject')return[]; const x={...f,metadata:{...(f.metadata||{}),critic_action:r.action,critic_reason:r.concise_reason}}; if(r.revised_severity&&['info','minor','major','critical'].includes(r.revised_severity))x.severity=r.revised_severity;if(r.revised_recommendation)x.recommendation=r.revised_recommendation;return[x]});
const uniq=[];const seen=new Set();for(const f of findings){const k=`${f.code}|${f.observation}`;if(!seen.has(k)){seen.add(k);uniq.push(f)}}findings=uniq;
const securityBlocked=findings.some(f=>f.code==='SUSPECTED_PROMPT_INJECTION'&&f.severity==='critical');
const policyConflicts=findings.filter(f=>String(f.code).includes('POLICY_CONFLICT')).map(f=>({finding_ref:f.finding_ref,observation:f.observation,required_action:f.recommendation}));
const insufficient=findings.some(f=>['ASSESSMENT_BRIEF_MISSING','RUBRIC_MISSING','LEARNING_OUTCOMES_MISSING','ARTIFACT_TEXT_UNAVAILABLE'].includes(f.code)&&['major','critical'].includes(f.severity));
let disposition='ready_for_human_approval';
if(securityBlocked)disposition='blocked_security';else if(policyConflicts.length)disposition='policy_conflict_requires_review';else if(insufficient)disposition='insufficient_evidence';else if(findings.some(f=>['major','critical'].includes(f.severity)))disposition='major_revision';else if(findings.some(f=>f.severity==='minor'))disposition='minor_revision';
function ratingFor(category){const f=findings.filter(x=>x.category===category||String(x.category).includes(category));if(!f.length)return{rating:3,confidence:0.6,note:'No verified adverse finding'};if(f.some(x=>x.severity==='critical'))return{rating:1,confidence:Math.max(...f.map(x=>Number(x.confidence||0.5))),note:'Critical finding'};if(f.some(x=>x.severity==='major'))return{rating:2,confidence:Math.max(...f.map(x=>Number(x.confidence||0.5))),note:'Major revision required'};if(f.some(x=>x.severity==='minor'))return{rating:3,confidence:Math.max(...f.map(x=>Number(x.confidence||0.5))),note:'Minor revision advised'};return{rating:4,confidence:0.75,note:'No material issue verified'}}
const aiSpecialist=(ctx.specialist_outputs||[]).map(x=>x.output||x).find(x=>x.specialist_key==='ai_use_design');
const aiDraft=draft.ai_use_design||{};
const report={schema_version:'1.0',case_id:ctx.case_id,recommended_disposition:disposition,executive_summary:String(draft.executive_summary||ctx.critic?.critic_summary||`Moderation produced ${findings.length} verified finding(s). Human approval remains required.`),assessment_profile:draft.assessment_profile||ctx.assessment_profile||{},scorecard:{outcome_alignment:draft.scorecard?.outcome_alignment||ratingFor('outcome_alignment'),rubric_quality:draft.scorecard?.rubric_quality||ratingFor('rubric'),assessment_validity:draft.scorecard?.assessment_validity||ratingFor('assessment_validity'),ai_use_design:draft.scorecard?.ai_use_design||ratingFor('ai_use'),policy_compliance:draft.scorecard?.policy_compliance||ratingFor('policy')},findings,uncertainties:[...(draft.uncertainties||[]),...(ctx.specialist_outputs||[]).flatMap(x=>(x.output||x).uncertainties||[])],policy_conflicts:policyConflicts,alignment_matrix:draft.alignment_matrix||((ctx.specialist_outputs||[]).map(x=>x.output||x).find(x=>x.specialist_key==='outcome_alignment')?.metrics?.alignment_matrix||[]),ai_use_design:{recommended_mode:aiDraft.recommended_mode||aiSpecialist?.metrics?.recommended_mode||'undetermined',permitted:Array.isArray(aiDraft.permitted)?aiDraft.permitted:[],prohibited:Array.isArray(aiDraft.prohibited)?aiDraft.prohibited:[],required_evidence:Array.isArray(aiDraft.required_evidence)?aiDraft.required_evidence:[],student_declaration:aiDraft.student_declaration||null},required_human_decisions:draft.required_human_decisions||findings.filter(f=>f.human_judgment_required).map(f=>`${f.finding_ref}: ${f.recommendation}`),provenance:{workflow_version:$env.AMAS_WORKFLOW_VERSION||'unknown',prompt_manifest:{report_synthesis:{version:built.prompt_version,hash:built.prompt_hash},specialists:Object.fromEntries((ctx.specialist_outputs||[]).map(x=>[x.specialist_key,{version:x.prompt_version,hash:x.prompt_hash}]))},corpus_version:$env.AMAS_CORPUS_VERSION||null,model_manifest:{primary:$env.LLM_PRIMARY_MODEL,critic:$env.LLM_CRITIC_MODEL,provider:$env.LLM_PROVIDER_NAME||'openai-compatible'},n8n_execution_id:$execution.id,input_hashes:ctx.provenance_seed?.input_hashes||{}}};
return [{json:{case_id:ctx.case_id,report,prompt_version_id:built.prompt_version_id,prompt_version:built.prompt_version,prompt_hash:built.prompt_hash,model:built.llm_request.model,raw_response:raw,llm_request:built.llm_request,latency_ms:Date.now()-built.started_at_ms}}];
"""
    store_sql=r"""
WITH lock_case AS MATERIALIZED (
 SELECT pg_advisory_xact_lock(hashtextextended($1::text,0)) AS locked
), agent AS (
 INSERT INTO amas.agent_runs(case_id,specialist_key,prompt_version_id,model,model_provider,request_hash,request,response,parsed_output,status,latency_ms,n8n_execution_id,completed_at)
 VALUES($1::uuid,'report_synthesis',$2::uuid,$3,$4,encode(digest($5::text,'sha256'),'hex'),$5::jsonb,$6::jsonb,$7::jsonb,'completed',$8,$9,now()) RETURNING id
), report_ins AS (
 INSERT INTO amas.reports(case_id,report_version,schema_version,disposition,report,report_sha256,workflow_version,prompt_manifest,corpus_version,model_manifest,status)
 SELECT $1::uuid,amas.next_report_version($1::uuid),'1.0',($7::jsonb->>'recommended_disposition')::amas.report_disposition,$7::jsonb,
   encode(digest($7::text,'sha256'),'hex'),$7::jsonb#>>'{provenance,workflow_version}',COALESCE($7::jsonb#>'{provenance,prompt_manifest}','{}'::jsonb),
   $7::jsonb#>>'{provenance,corpus_version}',COALESCE($7::jsonb#>'{provenance,model_manifest}','{}'::jsonb),'draft'
 FROM lock_case
 RETURNING id,report_version,report
), findings_ins AS (
 INSERT INTO amas.findings(case_id,report_id,agent_run_id,finding_ref,code,category,severity,observation,interpretation,recommendation,confidence,human_judgment_required,evidence,verification_status,critic_status,metadata)
 SELECT $1::uuid,r.id,a.id,f->>'finding_ref',f->>'code',f->>'category',(f->>'severity')::amas.finding_severity,f->>'observation',NULLIF(f->>'interpretation',''),f->>'recommendation',NULLIF(f->>'confidence','')::numeric,COALESCE((f->>'human_judgment_required')::boolean,true),COALESCE(f->'evidence','[]'::jsonb),COALESCE(f->>'verification_status','verified'),f#>>'{metadata,critic_action}',COALESCE(f->'metadata','{}'::jsonb)
 FROM report_ins r CROSS JOIN agent a CROSS JOIN LATERAL jsonb_array_elements(r.report->'findings') f RETURNING id
), upd AS (
 UPDATE amas.cases SET latest_report_id=r.id,status='awaiting_review' FROM report_ins r WHERE amas.cases.id=$1::uuid RETURNING amas.cases.id
), audit AS (
 SELECT amas.append_audit($1::uuid,'system','report_synthesis','report_created','report',r.id::text,jsonb_build_object('version',r.report_version,'disposition',r.report->>'recommended_disposition'),NULL,$9) FROM report_ins r
)
SELECT jsonb_build_object('case_id',$1,'report_id',r.id::text,'report_version',r.report_version,'report',r.report,'status','awaiting_review') AS output FROM report_ins r;
"""
    normalize_archive_js=r"""
const stored=$('Store Report and Findings').item.json.output;
const response=$json||{};
const archiveOk=!response.error && Boolean(response.storage_bucket) && Boolean(response.storage_key) && Boolean(response.sha256);
const warning=archiveOk?null:{code:'REPORT_OBJECT_ARCHIVE_FAILED',message:String(response.error?.message||response.message||'The canonical report remains stored in PostgreSQL, but its object-storage archive was not created.')};
return [{json:{report_id:stored.report_id,storage_bucket:archiveOk?response.storage_bucket:'',storage_key:archiveOk?response.storage_key:'',sha256:archiveOk?response.sha256:'',archive_ok:archiveOk,warning,stored_output:stored}}];
"""
    archive_sql=r"""
WITH upd AS (
 UPDATE amas.reports
 SET storage_bucket=NULLIF($2,''), storage_key=NULLIF($3,'')
 WHERE id=$1::uuid AND NULLIF($2,'') IS NOT NULL AND NULLIF($3,'') IS NOT NULL
 RETURNING id
)
SELECT (
  $4::jsonb
  || CASE WHEN $6::boolean
       THEN jsonb_build_object('storage',jsonb_build_object('bucket',$2,'key',$3,'sha256',$5::text,'archived',true))
       ELSE jsonb_build_object('storage',jsonb_build_object('archived',false),'warnings',jsonb_build_array($7::jsonb))
     END
) AS output;
"""
    nodes=[
      webhook(key,"Synthesis Webhook","POST","amas/internal/synthesize",(0,0)),
      code(key,"Authenticate",INTERNAL_AUTH_JS,(200,0)),
      postgres(key,"Load Synthesis Prompt",load_sql,"={{ ['report_synthesis',JSON.stringify($json)] }}",(420,0)),
      code(key,"Build Synthesis Request",build_js,(650,0)),
      http(key,"Call Synthesis Model","={{ $env.LLM_BASE_URL.replace(/\\/$/, '') + '/chat/completions' }}","={{ JSON.stringify($json.llm_request) }}",(900,0),credentials=LLM_CREDENTIAL,timeout=360000),
      code(key,"Finalize Canonical Report",finalize_js,(1140,0)),
      postgres(key,"Store Report and Findings",store_sql,"={{ [$json.case_id,$json.prompt_version_id,$json.model,$env.LLM_PROVIDER_NAME || 'openai-compatible',JSON.stringify($json.llm_request),JSON.stringify($json.raw_response),JSON.stringify($json.report),$json.latency_ms,$execution.id] }}",(1390,0)),
      http(key,"Archive Report Object","={{ $env.AMAS_INTAKE_INTERNAL_URL.replace(/\\/$/, '') + '/internal/reports' }}","={{ JSON.stringify({case_id:$json.output.case_id,report_id:$json.output.report_id,report_version:$json.output.report_version,tenant_id:$('Build Synthesis Request').item.json.context.case_bundle?.case?.tenant_id || 'default',report:$json.output.report}) }}",(1630,0),headers=[{"name":"X-AMAS-Internal-Token","value":"={{ $env.AMAS_INTERNAL_TOKEN }}"}],timeout=120000,on_error="continueRegularOutput"),
      code(key,"Normalize Archive Result",normalize_archive_js,(1850,0)),
      postgres(key,"Record Report Object",archive_sql,"={{ [$json.report_id,$json.storage_bucket,$json.storage_key,JSON.stringify($json.stored_output),$json.sha256,$json.archive_ok,JSON.stringify($json.warning || {code:'REPORT_OBJECT_ARCHIVE_FAILED'})] }}",(2080,0)),
      respond(key,"Respond","={{ $json.output }}",(2320,0))
    ]
    c:dict[str,Any]={}
    for a,b in [("Synthesis Webhook","Authenticate"),("Authenticate","Load Synthesis Prompt"),("Load Synthesis Prompt","Build Synthesis Request"),("Build Synthesis Request","Call Synthesis Model"),("Call Synthesis Model","Finalize Canonical Report"),("Finalize Canonical Report","Store Report and Findings"),("Store Report and Findings","Archive Report Object"),("Archive Report Object","Normalize Archive Result"),("Normalize Archive Result","Record Report Object"),("Record Report Object","Respond")]:connect(c,a,b)
    write("23_report_synthesis.json",workflow(key,"AMAS 23 - Canonical Report Synthesis",nodes,c))


def report_api_workflow() -> None:
    key='31-report-api'
    auth_js=PUBLIC_AUTH_PREFIX+r"""
const caseId=String(($json.params||{}).caseId||($json.path||{}).caseId||body.case_id||'');
if(!/^[0-9a-fA-F-]{36}$/.test(caseId))throw new Error('Invalid case id');return [{json:{case_id:caseId}}];
"""
    query=r"""
SELECT jsonb_build_object(
  'case_id',c.id::text,
  'status',c.status,
  'report_id',r.id::text,
  'report_version',r.report_version,
  'report',r.report,
  'storage',CASE WHEN r.storage_key IS NULL THEN jsonb_build_object('archived',false) ELSE jsonb_build_object('archived',true,'bucket',r.storage_bucket,'key',r.storage_key) END,
  'created_at',r.created_at
) AS output
FROM amas.cases c LEFT JOIN amas.reports r ON r.id=c.latest_report_id WHERE c.id=$1::uuid;
"""
    nodes=[webhook(key,"Report Webhook","GET","amas/v1/cases/:caseId/report",(0,0)),code(key,"Authenticate and Parse",auth_js,(220,0)),postgres(key,"Load Latest Report",query,"={{ [$json.case_id] }}",(470,0)),respond(key,"Respond","={{ $json.output || {error:'case_not_found'} }}",(720,0))]
    c:dict[str,Any]={};connect(c,"Report Webhook","Authenticate and Parse");connect(c,"Authenticate and Parse","Load Latest Report");connect(c,"Load Latest Report","Respond")
    write("31_report_api.json",workflow(key,"AMAS 31 - Report API",nodes,c))


def review_workflow() -> None:
    key='30-human-review'
    validate_js=PUBLIC_AUTH_PREFIX+r"""
const decisions=['accept','accept_with_amendments','dismiss','request_rerun','escalate','approve','reject'];
for(const f of ['case_id','report_id','reviewer_id','decision'])if(!body[f])throw new Error(`Missing ${f}`);
if(!decisions.includes(body.decision))throw new Error('Unsupported review decision');
body.changes=body.changes||{};return [{json:body}];
"""
    query=r"""
WITH ins AS (
 INSERT INTO amas.review_actions(case_id,report_id,finding_id,reviewer_id,decision,comment,changes)
 VALUES($1::uuid,$2::uuid,NULLIF($3,'')::uuid,$4,$5::amas.review_decision,NULLIF($6,''),$7::jsonb) RETURNING id,decision
), report_upd AS (
 UPDATE amas.reports SET status=CASE WHEN $5='approve' THEN 'approved' WHEN $5='reject' THEN 'rejected' ELSE status END WHERE id=$2::uuid RETURNING id
), case_upd AS (
 UPDATE amas.cases SET status=CASE WHEN $5='approve' THEN 'approved'::amas.case_status WHEN $5='reject' THEN 'rejected'::amas.case_status WHEN $5='accept_with_amendments' THEN 'approved_with_changes'::amas.case_status ELSE status END WHERE id=$1::uuid RETURNING id,status
), audit AS (
 SELECT amas.append_audit($1::uuid,'user',$4,'review_action','report',$2,jsonb_build_object('decision',$5,'finding_id',NULLIF($3,'')),NULL,$8)
)
SELECT jsonb_build_object('review_action_id',ins.id::text,'case_id',$1,'report_id',$2,'decision',ins.decision,'case_status',case_upd.status) AS output FROM ins CROSS JOIN case_upd;
"""
    nodes=[webhook(key,"Review Webhook","POST","amas/v1/reviews",(0,0)),code(key,"Authenticate and Validate",validate_js,(240,0)),postgres(key,"Record Review",query,"={{ [$json.case_id,$json.report_id,$json.finding_id || '',$json.reviewer_id,$json.decision,$json.comment || '',JSON.stringify($json.changes),$execution.id] }}",(500,0)),respond(key,"Respond","={{ $json.output }}",(750,0))]
    c:dict[str,Any]={};connect(c,"Review Webhook","Authenticate and Validate");connect(c,"Authenticate and Validate","Record Review");connect(c,"Record Review","Respond")
    write("30_human_review.json",workflow(key,"AMAS 30 - Human Review Boundary",nodes,c))


def eval_workflow() -> None:
    key='40-eval-endpoint'
    parse_js=EVAL_AUTH_PREFIX+r"""
let payload=body.case_payload??body.prompt??body;
if(typeof payload==='string'){try{payload=JSON.parse(payload)}catch(e){throw new Error(`Evaluation prompt must contain JSON: ${e.message}`)}}
function uuidv4(){return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0,v=c==='x'?r:(r&3|8);return v.toString(16)})}
payload.case_id=payload.case_id||uuidv4();payload.idempotency_key=payload.idempotency_key||`eval-${payload.case_id}`;payload.evaluation_mode=true;payload.tenant_id=payload.tenant_id||'evaluation';return [{json:payload}];
"""
    shape_js=r"""
const response=$json;const report=response.report||response;return [{json:{output:JSON.stringify(report),metadata:{case_id:response.case_id,report_id:response.report_id,report_version:response.report_version,workflow_version:$env.AMAS_WORKFLOW_VERSION}}}];
"""
    nodes=[webhook(key,"Evaluation Webhook","POST","amas/eval/moderate",(0,0)),code(key,"Authenticate and Parse Case",parse_js,(250,0)),http(key,"Invoke Case Intake","={{ $env.N8N_INTERNAL_BASE_URL.replace(/\\/$/, '') + '/webhook/amas/v1/cases' }}","={{ JSON.stringify($json) }}",(520,0),headers=[{"name":"X-AMAS-API-Token","value":"={{ $env.AMAS_API_TOKEN }}"}],timeout=600000),code(key,"Shape Promptfoo Response",shape_js,(790,0)),respond(key,"Respond","={{ $json }}",(1030,0))]
    c:dict[str,Any]={};connect(c,"Evaluation Webhook","Authenticate and Parse Case");connect(c,"Authenticate and Parse Case","Invoke Case Intake");connect(c,"Invoke Case Intake","Shape Promptfoo Response");connect(c,"Shape Promptfoo Response","Respond")
    write("40_promptfoo_evaluation_endpoint.json",workflow(key,"AMAS 40 - Promptfoo Evaluation Endpoint",nodes,c))


def ingestion_workflow() -> None:
    key='90-knowledge-ingestion'
    validate_js=INTERNAL_AUTH_PREFIX+r"""
for(const f of ['source_id','title','version','authority_rank','authority_scope','sha256','text'])if(body[f]===undefined||body[f]===null||body[f]==='')throw new Error(`Missing ${f}`);
body.status=body.status||'active';body.metadata={...(body.metadata||{}),source_id:body.source_id,title:body.title,version:body.version,authority_rank:Number(body.authority_rank),authority_scope:body.authority_scope,status:body.status,locator:body.locator||'whole document'};return [{json:body}];
"""
    extract_location_js=r"""
const original=$('Authenticate and Validate').item.json;const raw=$json;const location=raw.location||raw.document?.location||raw.documents?.[0]?.location||raw.filename||raw.document?.filename;if(!location)throw new Error(`AnythingLLM upload response did not contain a document location: ${JSON.stringify(raw).slice(0,600)}`);return [{json:{...original,anythingllm_doc_location:location,upload_response:raw}}];
"""
    store_sql=r"""
INSERT INTO amas.policy_sources(source_id,title,version,authority_rank,authority_scope,status,effective_from,effective_to,anythingllm_doc_location,storage_bucket,storage_key,sha256,metadata)
VALUES($1,$2,$3,$4,$5,$6,NULLIF($7,'')::date,NULLIF($8,'')::date,$9,NULLIF($10,''),NULLIF($11,''),$12,$13::jsonb)
ON CONFLICT(source_id,version) DO UPDATE SET title=EXCLUDED.title,authority_rank=EXCLUDED.authority_rank,authority_scope=EXCLUDED.authority_scope,status=EXCLUDED.status,effective_from=EXCLUDED.effective_from,effective_to=EXCLUDED.effective_to,anythingllm_doc_location=EXCLUDED.anythingllm_doc_location,storage_bucket=EXCLUDED.storage_bucket,storage_key=EXCLUDED.storage_key,sha256=EXCLUDED.sha256,metadata=EXCLUDED.metadata
RETURNING jsonb_build_object('source_id',source_id,'version',version,'anythingllm_doc_location',anythingllm_doc_location,'status',status) AS output;
"""
    nodes=[webhook(key,"Knowledge Ingestion Webhook","POST","amas/internal/knowledge/ingest",(0,0)),code(key,"Authenticate and Validate",validate_js,(230,0)),http(key,"Upload Raw Text to AnythingLLM","={{ $env.ANYTHINGLLM_BASE_URL.replace(/\\/$/, '') + '/api/v1/document/raw-text' }}","={{ JSON.stringify({textContent:$json.text,metadata:$json.metadata}) }}",(500,0),credentials=ANYTHINGLLM_CREDENTIAL,timeout=180000),code(key,"Extract Document Location",extract_location_js,(750,0)),http(key,"Attach Document to Workspace","={{ $env.ANYTHINGLLM_BASE_URL.replace(/\\/$/, '') + '/api/v1/workspace/' + encodeURIComponent($env.ANYTHINGLLM_WORKSPACE_SLUG) + '/update-embeddings' }}","={{ JSON.stringify({adds:[$json.anythingllm_doc_location],deletes:[]}) }}",(1000,0),credentials=ANYTHINGLLM_CREDENTIAL,timeout=300000),postgres(key,"Store Policy Metadata",store_sql,"={{ [$('Extract Document Location').item.json.source_id,$('Extract Document Location').item.json.title,$('Extract Document Location').item.json.version,$('Extract Document Location').item.json.authority_rank,$('Extract Document Location').item.json.authority_scope,$('Extract Document Location').item.json.status,$('Extract Document Location').item.json.effective_from || '',$('Extract Document Location').item.json.effective_to || '',$('Extract Document Location').item.json.anythingllm_doc_location,$('Extract Document Location').item.json.storage_bucket || '',$('Extract Document Location').item.json.storage_key || '',$('Extract Document Location').item.json.sha256,JSON.stringify($('Extract Document Location').item.json.metadata)] }}",(1250,0)),respond(key,"Respond","={{ $json.output }}",(1500,0))]
    c:dict[str,Any]={}
    for a,b in [("Knowledge Ingestion Webhook","Authenticate and Validate"),("Authenticate and Validate","Upload Raw Text to AnythingLLM"),("Upload Raw Text to AnythingLLM","Extract Document Location"),("Extract Document Location","Attach Document to Workspace"),("Attach Document to Workspace","Store Policy Metadata"),("Store Policy Metadata","Respond")]:connect(c,a,b)
    write("90_knowledge_ingestion.json",workflow(key,"AMAS 90 - Authoritative Knowledge Ingestion",nodes,c))


def main() -> None:
    for p in OUT.glob('*.json'): p.unlink()
    health_workflow(); intake_workflow(); preflight_workflow(); retrieval_workflow()
    llm_workflow('09_assessment_profiler.json','AMAS 09 - Assessment Profiling Supervisor','amas/internal/profile','assessment_profiler','profiler')
    specs=[
      ('10_outcome_alignment.json','AMAS 10 - Outcome Alignment Specialist','outcome-alignment','outcome_alignment'),
      ('11_rubric_quality.json','AMAS 11 - Rubric Quality Specialist','rubric-quality','rubric_quality'),
      ('12_assessment_validity.json','AMAS 12 - Assessment Validity Specialist','assessment-validity','assessment_validity'),
      ('13_ai_use_design.json','AMAS 13 - AI Use Design Specialist','ai-use-design','ai_use_design'),
      ('14_policy_accessibility.json','AMAS 14 - Policy and Accessibility Specialist','policy-accessibility','policy_accessibility'),
      ('15_programming_assessment.json','AMAS 15 - Programming Assessment Specialist','programming-assessment','programming_assessment'),
      ('16_group_work.json','AMAS 16 - Group Work Specialist','group-work','group_work'),
    ]
    for fn,title,slug,pkey in specs: llm_workflow(fn,title,f'amas/internal/specialist/{slug}',pkey,'specialist')
    orchestrator_workflow(); evidence_workflow()
    llm_workflow('22_adversarial_critic.json','AMAS 22 - Adversarial Critic','amas/internal/critic','adversarial_critic','critic')
    synthesis_workflow(); review_workflow(); report_api_workflow(); eval_workflow(); ingestion_workflow()
    manifest=[]
    for p in sorted(OUT.glob('*.json')):
        data=json.loads(p.read_text())
        manifest.append({'file':p.name,'name':data['name'],'versionId':data['versionId'],'active':data['active']})
    (OUT/'manifest.json').write_text(json.dumps({'schema_version':'1.0','workflows':manifest},indent=2)+'\n')
    print(f'Generated {len(manifest)} workflows in {OUT}')


if __name__ == '__main__':
    main()
