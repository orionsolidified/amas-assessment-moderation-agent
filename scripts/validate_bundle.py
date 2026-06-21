#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

for path in sorted(ROOT.rglob("*.json")):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")

for path in sorted((ROOT / "sql").glob("*.sql")):
    # psql meta-commands are handled by the migration runner, not PostgreSQL's parser.
    sql = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("\\"))
    try:
        parse_sql(sql)
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)}: PostgreSQL syntax error: {exc}")

workflow_files = sorted((ROOT / "workflows").glob("[0-9][0-9]_*.json"))
if len(workflow_files) != 20:
    errors.append(f"Expected 20 generated workflow files; found {len(workflow_files)}")

webhook_paths: set[str] = set()
node_bin = shutil.which("node")

with tempfile.TemporaryDirectory(prefix="amas-js-check-") as temp_dir:
    temp_path = Path(temp_dir)
    for wf in workflow_files:
        obj = json.loads(wf.read_text(encoding="utf-8"))
        for key in ("name", "nodes", "connections", "settings"):
            if key not in obj:
                errors.append(f"{wf.name}: missing {key}")

        names = [n.get("name") for n in obj.get("nodes", [])]
        if len(names) != len(set(names)):
            errors.append(f"{wf.name}: duplicate node name")
        name_set = set(names)

        for src, outputs in obj.get("connections", {}).items():
            if src not in name_set:
                errors.append(f"{wf.name}: connection source {src!r} missing")
            for groups in outputs.values():
                for group in groups:
                    for link in group:
                        if link.get("node") not in name_set:
                            errors.append(f"{wf.name}: target {link.get('node')!r} missing")

        for index, n in enumerate(obj.get("nodes", [])):
            if n.get("type") == "n8n-nodes-base.postgres":
                query = n.get("parameters", {}).get("query")
                if not isinstance(query, str):
                    errors.append(f"{wf.name}: PostgreSQL node {n.get('name')!r} has no query")
                else:
                    try:
                        parse_sql(query)
                    except Exception as exc:
                        errors.append(f"{wf.name}: PostgreSQL syntax error in {n.get('name')!r}: {exc}")

            if n.get("type") == "n8n-nodes-base.webhook":
                path = n.get("parameters", {}).get("path")
                if path in webhook_paths:
                    errors.append(f"{wf.name}: duplicate webhook path {path!r}")
                webhook_paths.add(path)

            if node_bin and n.get("type") == "n8n-nodes-base.code":
                js = n.get("parameters", {}).get("jsCode")
                if not isinstance(js, str):
                    errors.append(f"{wf.name}: Code node {n.get('name')!r} has no jsCode")
                    continue
                # n8n Code-node snippets permit top-level return, whereas node --check
                # expects a script. Wrapping in a function preserves syntax checking.
                js_path = temp_path / f"{wf.stem}-{index}.js"
                js_path.write_text(f"async function __n8n_code__() {{\n{js}\n}}\n", encoding="utf-8")
                proc = subprocess.run(
                    [node_bin, "--check", str(js_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode:
                    detail = (proc.stderr or proc.stdout).strip()
                    errors.append(f"{wf.name}: JavaScript syntax error in {n.get('name')!r}: {detail}")

if errors:
    raise SystemExit("\n".join(errors))

js_note = " including Code-node JavaScript" if node_bin else " (Node.js unavailable; Code-node JavaScript not checked)"
print(f"Validated JSON, PostgreSQL syntax, webhook uniqueness, and workflow graph structure{js_note} under {ROOT}")
