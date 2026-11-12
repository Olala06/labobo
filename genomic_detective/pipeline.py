from __future__ import annotations

from pathlib import Path
from typing import Any

from .dataset import load_case, parse_phenotypes
from .knowledge import load_knowledge
from .models import CaseInput
from .ranking import load_ranking_config, rank_candidates
from .reporting import write_reports


def analyze_case(case: CaseInput, knowledge: dict[str, Any] | None = None) -> dict[str, Any]:
    knowledge = knowledge or load_knowledge()
    hits = parse_phenotypes(case.phenotype_text, knowledge)
    candidates = rank_candidates(case, hits, knowledge)
    complete = bool(case.variants) and bool(hits) and not case.warnings
    if not hits:
        status = "incomplete"
    elif not case.variants:
        status = "incomplete"
    elif candidates:
        status = "candidate" if candidates[0].status == "candidate" else "uncertain"
    else:
        status = "no_convincing_candidate"
    ranking_config = load_ranking_config()
    return {
        "case_name": case.name,
        "status": status,
        "complete": complete,
        "phenotype_text": case.phenotype_text,
        "recognized_phenotypes": [hit.to_dict() for hit in hits],
        "unmatched_phenotype_note": None if hits else "Словарь HPO не распознал признаки. Расширьте формулировки/словарь; отсутствие совпадения не означает отсутствие фенотипа.",
        "variant_count": len(case.variants),
        "variants": [variant.to_dict() for variant in case.variants],
        "source_files": case.source_files,
        "warnings": case.warnings,
        "weights": ranking_config["weights"],
        "score_interpretation": "Эвристический исследовательский балл для ранжирования; НЕ вероятность заболевания и НЕ клиническая оценка.",
        "candidates": [candidate.to_dict() for candidate in candidates],
        "limitations": [
            "Курируемая база фенотипов и заболеваний ограничена и не является полной HPO/геномной базой.",
            "Молекулярная оценка не заменяет точное allele-disease-transcript сопоставление, review status и клиническую интерпретацию.",
            "Генотипы из VCF не устанавливают de novo, сегрегацию, фазу trans/cis, качество покрытия или фенотипическую пенетрантность.",
            "VUS, conflicting interpretations, benign/likely benign не добавляют положительную молекулярную поддержку.",
            "Не найденный кандидат не исключает генетическую причину.",
        ],
    }


def analyze_path(path: Path, output_dir: Path, phenotype_text: str = "") -> list[dict[str, Any]]:
    cases = [load_case(path, phenotype_text)]
    reports = [analyze_case(case) for case in cases]
    write_reports(reports, output_dir)
    return reports
