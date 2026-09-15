from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
REGISTRY_PATH = PROMPTS_DIR / "registry.json"


def load_registry() -> Dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def get_prompt_metadata(role: str) -> Dict[str, Any]:
    registry = load_registry()
    if role not in registry["roles"]:
        raise KeyError(f"Prompt role not found: {role}")
    meta = dict(registry["roles"][role])
    meta["role"] = role
    return meta
