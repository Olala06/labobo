from __future__ import annotations

from typing import Any

from .experts import run_experts
from .models import Candidate, CaseInput, PhenotypeHit

WEIGHTS = {"phenotype": 0.55, "molecular": 0.35, "inheritance": 0.10}


def rank_candidates(case: CaseInput, hits: list[PhenotypeHit], knowledge: dict[str, Any]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for condition in knowledge["conditions"]:
        experts = run_experts(condition, case, hits)
        score = sum(WEIGHTS[name] * experts[name].score for name in WEIGHTS)
        if not any(result.score > 0 for result in experts.values()):
            continue
        sorted_scores = sorted((result.score for result in experts.values()), reverse=True)
        status = "candidate" if score >= 0.35 else "uncertain"
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
            score=score,
            status=status,
            experts=experts,
            sources=[{"label": str(s["label"]), "url": str(s["url"])} for s in condition.get("sources", [])],
            explanation=explanation,
        ))
    return sorted(candidates, key=lambda item: item.score, reverse=True)
