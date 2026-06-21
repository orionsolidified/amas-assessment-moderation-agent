#!/usr/bin/env python3
"""Load versioned AMAS prompts into PostgreSQL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("AMAS_DATABASE_URL"))
    parser.add_argument("--prompts-dir", type=Path, default=Path(__file__).resolve().parents[1] / "prompts")
    parser.add_argument("--created-by", default="bootstrap")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("Provide --dsn or AMAS_DATABASE_URL")

    manifest = json.loads((args.prompts_dir / "manifest.json").read_text(encoding="utf-8"))
    shared = (args.prompts_dir / "_shared_system.md").read_text(encoding="utf-8").strip()

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            for item in manifest["prompts"]:
                system = (args.prompts_dir / item["system"]).read_text(encoding="utf-8").replace("{{SHARED_SYSTEM}}", shared).strip()
                user = (args.prompts_dir / item["user"]).read_text(encoding="utf-8").strip()
                schema_path = (args.prompts_dir / item["schema"]).resolve()
                output_schema = json.loads(schema_path.read_text(encoding="utf-8"))
                digest = sha256_text(json.dumps({
                    "system": system,
                    "user": user,
                    "schema": output_schema,
                    "model_config": item.get("model_config", {}),
                }, sort_keys=True, ensure_ascii=False))
                cur.execute("UPDATE amas.prompt_versions SET active = FALSE WHERE prompt_key = %s", (item["key"],))
                cur.execute(
                    """
                    INSERT INTO amas.prompt_versions
                      (prompt_key, version, system_prompt, user_template, output_schema, model_config, content_sha256, active, created_by)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,TRUE,%s)
                    ON CONFLICT (prompt_key, version) DO UPDATE SET
                      system_prompt = EXCLUDED.system_prompt,
                      user_template = EXCLUDED.user_template,
                      output_schema = EXCLUDED.output_schema,
                      model_config = EXCLUDED.model_config,
                      content_sha256 = EXCLUDED.content_sha256,
                      active = TRUE,
                      created_by = EXCLUDED.created_by
                    """,
                    (
                        item["key"], item["version"], system, user,
                        json.dumps(output_schema), json.dumps(item.get("model_config", {})),
                        digest, args.created_by,
                    ),
                )
                print(f"loaded {item['key']}@{item['version']} {digest[:12]}")
        conn.commit()


if __name__ == "__main__":
    main()
