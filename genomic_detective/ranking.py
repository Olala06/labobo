from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .experts import run_experts
from .models import Candidate, CaseInput, PhenotypeHit

_ROOT = Path(__file__).resolve().parents[1]


def load_ranking_config() -> dict[str, Any]:
    config_path = _ROOT / "config" / "ranking.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    weights = config["weights"]
    if set(weights) != {"phenotype", "molecular", "inheritance"}:
        raise ValueError("ranking.json must define phenotype, molecular and inheritance weights")
    if abs(sum(float(v) for v in weights.values()) - 1.0) > 1e-9:
        raise ValueError("ranking weights must sum to 1.0")
    return config


def rank_candidates(case: CaseInput, hits: list[PhenotypeHit], knowledge: dict[str, Any]) -> list[Candidate]:
    config = load_ranking_config()
    weights = config["weights"]
    candidates: list[Candidate] = []
    for condition in knowledge["conditions"]:
        experts = run_experts(condition, case, hits)
        score = sum(float(weights[name]) * experts[name].score for name in weights)
        if not any(result.score > 0 for result in experts.values()):
            continue
        sorted_scores = sorted((result.score for result in experts.values()), reverse=True)
        status = "candidate" if score >= float(config["candidate_threshold"]) else "uncertain"
        if sorted_scores[0] - sorted_scores[-1] < 0.10:
            status = "uncertain"
        explanation = []
        for name, title in (("phenotype", "Фенотип"), ("molecular", "Молекулярные данные"), ("inheritance", "Наследование")):
            result = experts[name]
            explanation.append(f"{title}: {result.score * 100:.0f}/100 по внутренней шкале.")
            explanation.extend(result.evidence)
        candidates.append(Candidate(
            condition_id=str(condition.get("id", condition["name"].lower().replace(" ", "_"))),
            name=str(condition["name"]),
            genes=[str(g) for g in condition.get("genes", [])],
            inheritance=str(condition.get("inheritance", "unknown")),
            score=score, status=status, experts=experts,
            sources=[{"label": str(s["label"]), "url": str(s["url"])} for s in condition.get("sources", [])],
            explanation=explanation,
            mechanism=str(condition.get("mechanism")) if condition.get("mechanism") else None,
        ))
    return sorted(candidates, key=lambda item: item.score, reverse=True)
