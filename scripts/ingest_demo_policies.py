#!/usr/bin/env python3
"""Ingest the synthetic demonstration policy corpus through AMAS workflow 90."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "samples" / "policies"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def field(text: str, label: str, default: str = "") -> str:
    match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", text, re.I)
    return match.group(1).strip() if match else default


def post(url: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AMAS-Internal-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def main() -> None:
    load_env(ROOT / "deploy" / ".env")
    base = os.environ.get("WEBHOOK_URL", "http://localhost:5678/").rstrip("/")
    token = os.environ.get("AMAS_INTERNAL_TOKEN", "")
    if not token:
        raise SystemExit("AMAS_INTERNAL_TOKEN is not configured")
    endpoint = f"{base}/webhook/amas/internal/knowledge/ingest"
    ranks = {"UNIV-ASSESS-001": 100, "FAC-AI-002": 80, "ACCESS-003": 70}
    scopes = {"UNIV-ASSESS-001": "university", "FAC-AI-002": "faculty", "ACCESS-003": "university"}
    for path in sorted(POLICY_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        source_id = field(text, "Source ID", path.stem)
        payload = {
            "source_id": source_id,
            "title": text.splitlines()[0].lstrip("# ").strip(),
            "version": field(text, "Version", "1.0-demo"),
            "authority_rank": ranks.get(source_id, 50),
            "authority_scope": scopes.get(source_id, "department"),
            "status": "active",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text,
            "metadata": {"synthetic": True, "filename": path.name},
        }
        result = post(endpoint, token, payload)
        print(source_id, json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
