from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import yaml
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_json_is_valid():
    for path in ROOT.rglob("*.json"):
        load_json(path)


def test_yaml_is_valid():
    for path in ROOT.rglob("*.yaml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))
    for path in ROOT.rglob("*.yml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))


def test_sample_intakes_conform_to_schema():
    schema = load_json(ROOT / "schemas" / "intake.schema.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    paths = [ROOT / "samples" / "demo_case.json", *(ROOT / "evals" / "cases").glob("*.json")]
    for path in paths:
        errors = sorted(validator.iter_errors(load_json(path)), key=lambda e: list(e.path))
        assert not errors, f"{path}: {[e.message for e in errors]}"


def test_sample_report_conforms_to_schema():
    specialist = load_json(ROOT / "schemas" / "specialist-output.schema.json")
    report = load_json(ROOT / "schemas" / "report.schema.json")
    # Resolve the report's relative reference without network access.
    registry = Registry().with_resources([
        (specialist["$id"], Resource.from_contents(specialist)),
        (report["$id"], Resource.from_contents(report)),
    ])
    validator = jsonschema.Draft202012Validator(report, registry=registry, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(load_json(ROOT / "samples" / "sample_report.json")), key=lambda e: list(e.path))
    assert not errors, [e.message for e in errors]


def test_prompt_manifest_integrity():
    manifest = load_json(ROOT / "prompts" / "manifest.json")
    keys = set()
    for item in manifest["prompts"]:
        assert item["key"] not in keys
        keys.add(item["key"])
        assert (ROOT / "prompts" / item["system"]).exists()
        assert (ROOT / "prompts" / item["user"]).exists()
        assert (ROOT / "prompts" / item["schema"]).resolve().exists()
    expected = {
        "assessment_profiler", "outcome_alignment", "rubric_quality", "assessment_validity",
        "ai_use_design", "policy_accessibility", "programming_assessment", "group_work",
        "adversarial_critic", "report_synthesis",
    }
    assert expected <= keys


def test_workflow_graphs_and_paths():
    paths = set()
    files = sorted((ROOT / "workflows").glob("[0-9][0-9]_*.json"))
    assert len(files) == 20
    for path in files:
        wf = load_json(path)
        assert {"name", "nodes", "connections", "settings", "versionId"} <= set(wf)
        names = [n["name"] for n in wf["nodes"]]
        ids = [n["id"] for n in wf["nodes"]]
        assert len(names) == len(set(names)), path
        assert len(ids) == len(set(ids)), path
        name_set = set(names)
        for source, outputs in wf["connections"].items():
            assert source in name_set
            for group in outputs.get("main", []):
                for edge in group:
                    assert edge["node"] in name_set
        for n in wf["nodes"]:
            if n["type"] == "n8n-nodes-base.webhook":
                webhook_path = n["parameters"]["path"]
                assert webhook_path not in paths, webhook_path
                paths.add(webhook_path)
    assert "amas/v1/cases" in paths
    assert "amas/internal/orchestrate" in paths
    assert "amas/eval/moderate" in paths


def test_workflows_do_not_embed_real_secrets_or_generic_dangerous_nodes():
    forbidden_node_types = {
        "n8n-nodes-base.executeCommand",
        "n8n-nodes-base.ssh",
        "n8n-nodes-base.readWriteFile",
        "n8n-nodes-base.emailSend",
    }
    for path in (ROOT / "workflows").glob("[0-9][0-9]_*.json"):
        raw = path.read_text(encoding="utf-8")
        assert "sk-" not in raw
        wf = json.loads(raw)
        assert not ({n["type"] for n in wf["nodes"]} & forbidden_node_types)


def test_compose_environment_is_documented():
    compose_text = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    referenced = set(re.findall(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", compose_text))
    declared = {line.split("=", 1)[0] for line in example.splitlines() if line and not line.startswith("#") and "=" in line}
    assert referenced <= declared, sorted(referenced - declared)
