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
    # Keep the small hand-curated disease table as a clearly labeled secondary
    # reference; the main gene prioritization comes from the full PyHPO annotations.
    legacy_hits = parse_phenotypes(case.phenotype_text, knowledge)
    candidates = rank_candidates(case, legacy_hits, knowledge)

    hpo_metadata: dict[str, Any] = {
        "library": "PyHPO",
        "version": "4.0.0",
        "similarity": "funSimAvg with gene information content",
        "status": "unavailable",
    }
    gene_candidates: list[dict[str, Any]] = []
    recognized_phenotypes: list[dict[str, str]] = []
    unmatched_phenotypes: list[str] = []
    hpo_error = None
    try:
        from .hpo import get_hpo_engine
        engine = get_hpo_engine()
        profile = engine.resolve(case.phenotype_text)
        recognized_phenotypes = profile["recognized"]
        unmatched_phenotypes = profile["unmatched"]
        gene_candidates = engine.rank_genes(case.variants, profile["terms"])
        hpo_metadata["status"] = "ready"
        hpo_metadata["recognized_terms"] = len(recognized_phenotypes)
        hpo_metadata["candidate_genes"] = len(gene_candidates)
    except Exception as exc:
        hpo_error = f"{type(exc).__name__}: {exc}"
        hpo_metadata["error"] = hpo_error

    # Preserve legacy term recognition as a fallback and for regression tests;
    # it is deliberately not presented as a complete HPO knowledge base.
    if not recognized_phenotypes:
        recognized_phenotypes = [hit.to_dict() for hit in legacy_hits]

    if not recognized_phenotypes:
        status = "incomplete"
    elif not case.variants:
        status = "incomplete"
    elif candidates:
        status = "candidate" if candidates[0].status == "candidate" else "uncertain"
    elif gene_candidates:
        status = "uncertain"
    else:
        status = "no_convincing_candidate"

    ranking_config = load_ranking_config()
    warnings = list(case.warnings)
    warnings.extend([
        "PyHPO gene scores are semantic phenotype-similarity scores, not calibrated disease probabilities.",
        "HPO gene associations are curated knowledge; they do not establish that an uploaded variant is causal.",
        "GTEx normal-tissue expression is biological context only and does not establish disease mechanism or variant pathogenicity.",
        "A missing HPO or GTEx association is not evidence that a gene or tissue is uninvolved.",
    ])
    if hpo_error:
        warnings.append("PyHPO не загрузился; показан только резервный небольшой словарь фенотипов: " + hpo_error)
    if not any(variant.gene for variant in case.variants):
        warnings.append("В исходном файле не указаны символы генов. Для связи вариантов с генами включите VEP/GTEx-аннотацию или загрузите VCF с gene annotation.")
    if unmatched_phenotypes:
        warnings.append("Не удалось однозначно сопоставить части фенотипического текста с HPO: " + ", ".join(unmatched_phenotypes[:20]))
    if any("VUS" in str(variant.clinvar).upper() or "UNCERTAIN" in str(variant.clinvar).upper()
           for variant in case.variants if variant.clinvar):
        warnings.append("VUS/uncertain significance не считаются доказательством патогенности.")

    return {
        "case_name": case.name,
        "status": status,
        "complete": bool(case.variants) and bool(recognized_phenotypes),
        "phenotype_text": case.phenotype_text,
        "recognized_phenotypes": recognized_phenotypes,
        "unmatched_phenotypes": unmatched_phenotypes,
        "hpo_metadata": hpo_metadata,
        "gene_candidates": gene_candidates,
        "unmatched_phenotype_note": None if recognized_phenotypes else "HPO не распознал признаки. Используйте поиск HPO и выберите точные термины; отсутствие совпадения не означает отсутствие фенотипа.",
        "variant_count": len(case.variants),
        "variants": [variant.to_dict() for variant in case.variants],
        "source_files": case.source_files,
        "warnings": warnings,
        "weights": ranking_config["weights"],
        "score_interpretation": "Оценки HPO — семантическое сходство фенотипов и генных аннотаций, а не вероятность заболевания; баллы из локального словаря — отдельная эвристика.",
        "candidates": [candidate.to_dict() for candidate in candidates],
        "limitations": [
            "Локальный словарь заболеваний knowledge.json мал и показывается только как дополнительная демонстрационная справка; основное генное ранжирование использует PyHPO.",
            "PyHPO использует ассоциации ген–HPO из включённого в библиотеку набора masterdata; версия библиотеки и версия исходных данных могут отличаться.",
            "GTEx — экспрессия в нормальных тканях; повышенная экспрессия не доказывает патогенность или причинную связь с фенотипом.",
            "VEP/GTEx опциональны. Без VEP точность связи координаты с геном зависит от аннотации, уже присутствующей во входном VCF/TSV.",
            "Генотипы из VCF не устанавливают de novo, сегрегацию, фазу trans/cis, качество покрытия или клиническую пенетрантность.",
            "Не найденный кандидат не исключает генетическую причину.",
        ],
    }

def analyze_path(path: Path, output_dir: Path, phenotype_text: str = "") -> list[dict[str, Any]]:
    cases = [load_case(path, phenotype_text)]
    reports = [analyze_case(case) for case in cases]
    write_reports(reports, output_dir)
    return reports
