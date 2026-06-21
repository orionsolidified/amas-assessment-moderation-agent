#!/usr/bin/env python3
"""Create deploy/.env from .env.example with cryptographically random local-demo secrets."""
from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
template = ROOT / "deploy" / ".env.example"
out = ROOT / "deploy" / ".env"
if out.exists():
    raise SystemExit(f"Refusing to overwrite {out}")
text = template.read_text(encoding="utf-8")
replacements = {
    "CHANGE_ME_POSTGRES_OWNER_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_AMAS_APP_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_AMAS_READONLY_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_64_CHAR_RANDOM_ENCRYPTION_KEY": secrets.token_hex(32),
    "CHANGE_ME_64_CHAR_RANDOM_JWT_SECRET": secrets.token_hex(32),
    "CHANGE_ME_LONG_RANDOM_PUBLIC_API_TOKEN": secrets.token_urlsafe(48),
    "CHANGE_ME_LONG_RANDOM_INTERNAL_TOKEN": secrets.token_urlsafe(48),
    "CHANGE_ME_LONG_RANDOM_EVAL_TOKEN": secrets.token_urlsafe(48),
    "CHANGE_ME_64_HEX_RPC_SECRET": secrets.token_hex(32),
    "CHANGE_ME_GARAGE_ADMIN_TOKEN": secrets.token_urlsafe(40),
    "CHANGE_ME_GARAGE_METRICS_TOKEN": secrets.token_urlsafe(40),
    "GKCHANGE_ME_32_HEX": "GK" + secrets.token_hex(16),
    "CHANGE_ME_64_HEX": secrets.token_hex(32),
}
for old, new in replacements.items():
    text = text.replace(old, new)
# Keep external service credentials deliberately unresolved.
out.write_text(text, encoding="utf-8")
out.chmod(0o600)
print(f"Created {out} with mode 0600. Configure AnythingLLM and model-gateway values before launch.")
