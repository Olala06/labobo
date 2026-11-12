from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "knowledge.json"


def load_knowledge(path: Path | None = None) -> dict[str, Any]:
    source = path or KNOWLEDGE_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data.get("phenotype_terms"), list) or not isinstance(data.get("conditions"), list):
        raise ValueError("knowledge.json must contain phenotype_terms and conditions arrays")
    return data


def phenotype_dictionary(knowledge: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in knowledge["phenotype_terms"]:
        hpo_id = str(item["hpo"])
        result[hpo_id] = {
            "label": str(item["label"]),
            "aliases": [str(value) for value in item.get("aliases", [])],
        }
    return result
