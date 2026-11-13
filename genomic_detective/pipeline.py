from __future__ import annotations

from pathlib import Path
from typing import Any

from .dataset import load_case, parse_phenotypes
from .knowledge import load_knowledge
from .models import CaseInput, Variant
from .ranking import load_ranking_config, rank_candidates
from .reporting import write_reports


def _variant_string(variant: Variant) -> str:
    chrom = str(variant.chrom)
    if not chrom.lower().startswith("chr"):
        chrom = f"chr{chrom}"
    return f"{chrom}:{variant.pos}:{variant.ref}:{variant.alt}"


def _genotype_label(genotype: str | None) -> tuple[str, int | None]:
    if not genotype or genotype in {".", "./.", ".|."}:
        return "GT не указан", None
    alleles = genotype.replace("|", "/").split("/")
    called = [allele for allele in alleles if allele != "."]
    if not called:
        return f"{genotype} (нет вызова)", None
    alt_count = sum(1 for allele in called if allele not in {"0"})
    if alt_count == 0:
        return f"{genotype} (гомозиготный REF)", 0
    if len(called) == 2 and alt_count == 1:
        return f"{genotype} (гетерозиготный ALT)", 1
    if len(called) == 2 and alt_count == 2:
        return f"{genotype} (гомозиготный ALT)", 2
    return f"{genotype} ({alt_count} ALT из {len(called)})", alt_count


def _inheritance_context(
    gene: str | None,
    genotype: str | None,
    knowledge: dict[str, Any],
) -> tuple[str, str]:
    if not gene:
        return "Не оценивается: ген не аннотирован", ""
    related = [
        condition for condition in knowledge.get("conditions", [])
        if gene.upper() in {str(item).upper() for item in condition.get("genes", [])}
    ]
    modes = sorted({str(item.get("inheritance", "unknown")).upper() for item in related})
    if not modes:
        return "В локальном справочнике модель наследования не задана", ""
    genotype_text, alt_count = _genotype_label(genotype)
    mechanism = next((str(item["mechanism"]) for item in related if item.get("mechanism")), "")
    if "AD" in modes or "AUTOSOMAL DOMINANT" in modes:
        if alt_count and alt_count >= 1:
            assessment = (
                f"AD: {genotype_text}; наличие одного ALT-аллеля совместимо с моноаллельной моделью. "
                "Это не доказывает патогенность, de novo статус или сегрегацию."
            )
        elif alt_count == 0:
            assessment = f"AD: {genotype_text}; вариант не подтверждён в ALT-состоянии."
        else:
            assessment = "AD: GT отсутствует — аллельную совместимость оценить нельзя."
    elif "AR" in modes or "AUTOSOMAL RECESSIVE" in modes:
        if alt_count == 2:
            assessment = (
                f"AR: {genotype_text}; запись совместима с двумя ALT-копиями. "
                "Патогенность варианта должна быть оценена отдельно."
            )
        elif alt_count == 1:
            assessment = (
                f"AR: {genotype_text}; найден один ALT-аллель. Для рецессивной модели "
                "нужен второй причинный аллель и проверка trans-фазы."
            )
        else:
            assessment = "AR: GT отсутствует или ALT не обнаружен; модель проверить нельзя."
    else:
        assessment = f"Модель {', '.join(modes)}; GT: {genotype_text}."
    return assessment, mechanism


def _build_variant_candidates(
    case: CaseInput,
    gene_candidates: list[dict[str, Any]],
    knowledge: dict[str, Any],
) -> list[dict[str, Any]]:
    gene_by_symbol = {
        str(item.get("gene", "")).upper(): (rank, item)
        for rank, item in enumerate(gene_candidates, 1)
    }
    rows = []
    for variant in case.variants:
        gene = str(variant.gene).upper() if variant.gene else None
        ranked = gene_by_symbol.get(gene or "")
        rank, candidate = ranked if ranked else (None, {})
        inheritance, mechanism = _inheritance_context(variant.gene, variant.genotype, knowledge)
        positives = candidate.get("directly_matched_hpo", [])
        exclusions = candidate.get("excluded_conflicts", [])
        if not variant.gene:
            interpretation = "Символ гена отсутствует в VCF; вариант показан, но не может быть ранжирован по HPO."
        elif rank:
            interpretation = (
                f"Ген занимает {rank}-е место по HPO-сходству; балл не является вероятностью "
                "и не доказывает причинность варианта."
            )
        else:
            interpretation = "Для гена не рассчитано HPO-сходство по доступным аннотациям."
        gnomad_af = (
            variant.info.get("gnomAD_AF")
            or variant.info.get("gnomADg_AF")
            or variant.info.get("GNOMAD_AF")
            or "NA (не предоставлено)"
        )
        rows.append({
            "rank": rank,
            "gene": variant.gene or "не аннотирован",
            "variant": _variant_string(variant),
            "genotype": variant.genotype or "NA",
            "genotype_label": _genotype_label(variant.genotype)[0],
            "consequence": variant.consequence or "NA (не аннотировано)",
            "gnomad_af": str(gnomad_af),
            "clinvar": variant.clinvar or "NA (не предоставлено)",
            "positive_matches": positives,
            "excluded_conflicts": exclusions,
            "hpo_score": candidate.get("adjusted_hpo_score_percent"),
            "inheritance_assessment": inheritance,
            "mechanism": mechanism,
            "interpretation": interpretation,
        })
    return sorted(rows, key=lambda item: (
        item["rank"] is None,
        item["rank"] if item["rank"] is not None else 10**9,
        item["variant"],
    ))


def analyze_case(case: CaseInput, knowledge: dict[str, Any] | None = None) -> dict[str, Any]:
    knowledge = knowledge or load_knowledge()
    legacy_hits = parse_phenotypes(case.phenotype_text, knowledge)
    candidates = rank_candidates(case, legacy_hits, knowledge)

    hpo_metadata: dict[str, Any] = {
        "library": "PyHPO",
        "version": "4.0.0",
        "similarity": "funSimAvg with gene information content",
        "exclusion_handling": "exact gene-HPO annotation conflict; conservative heuristic",
        "status": "unavailable",
    }
    gene_candidates: list[dict[str, Any]] = []
    recognized_phenotypes: list[dict[str, str]] = []
    excluded_phenotypes: list[dict[str, str]] = []
    unmatched_phenotypes: list[str] = []
    unmatched_excluded: list[str] = []
    hpo_error = None
    try:
        from .hpo import get_hpo_engine
        engine = get_hpo_engine()
        profile = engine.resolve(case.phenotype_text)
        excluded_profile = engine.resolve(case.excluded_phenotype_text)
        recognized_phenotypes = profile["recognized"]
        excluded_phenotypes = excluded_profile["recognized"]
        unmatched_phenotypes = profile["unmatched"]
        unmatched_excluded = excluded_profile["unmatched"]
        gene_candidates = engine.rank_genes(
            case.variants, profile["terms"], excluded_profile["terms"]
        )
        hpo_metadata["status"] = "ready"
        hpo_metadata["recognized_terms"] = len(recognized_phenotypes)
        hpo_metadata["excluded_terms"] = len(excluded_phenotypes)
        hpo_metadata["candidate_genes"] = len(gene_candidates)
    except Exception as exc:
        hpo_error = f"{type(exc).__name__}: {exc}"
        hpo_metadata["error"] = hpo_error

    if not recognized_phenotypes:
        recognized_phenotypes = [hit.to_dict() for hit in legacy_hits]

    variant_candidates = _build_variant_candidates(case, gene_candidates, knowledge)
    prediction = next(
        (item["variant"] for item in variant_candidates if item.get("rank") is not None),
        "no_causal_variant_in_vcf",
    )

    if not recognized_phenotypes or not case.variants:
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
        "Рейтинг HPO — семантическое сходство фенотипов с аннотациями генов, а не вероятность заболевания.",
        "Excluded HPO учитываются как консервативные точные конфликты с аннотациями гена; отсутствие конфликта не доказывает отсутствие признака.",
        "Генное совпадение не доказывает причинность конкретного варианта.",
        "NA означает, что аннотация не была предоставлена или получена, а не доброкачественность варианта.",
        "GT из одного VCF не устанавливает de novo статус, семейную сегрегацию или фазу trans/cis.",
        "no_causal_variant_in_vcf означает, что вариант не удалось приоритизировать по имеющимся входным данным; это не исключает генетическую причину.",
    ])
    if hpo_error:
        warnings.append("PyHPO не загрузился; показан только резервный небольшой словарь фенотипов: " + hpo_error)
    if not any(variant.gene for variant in case.variants):
        warnings.append("В VCF не указаны символы генов. Включите опциональную VEP-аннотацию GRCh38 либо используйте файл с функциональной аннотацией.")
    if unmatched_phenotypes:
        warnings.append("Не сопоставлены положительные фенотипы: " + ", ".join(unmatched_phenotypes[:20]))
    if unmatched_excluded:
        warnings.append("Не сопоставлены excluded-фенотипы: " + ", ".join(unmatched_excluded[:20]))
    if any("VUS" in str(variant.clinvar).upper() or "UNCERTAIN" in str(variant.clinvar).upper()
           for variant in case.variants if variant.clinvar):
        warnings.append("VUS/uncertain significance не считаются доказательством патогенности.")

    return {
        "case_name": case.name,
        "case_id": case.name,
        "status": status,
        "complete": bool(case.variants) and bool(recognized_phenotypes),
        "prediction": prediction,
        "phenotype_text": case.phenotype_text,
        "excluded_phenotype_text": case.excluded_phenotype_text,
        "recognized_phenotypes": recognized_phenotypes,
        "excluded_phenotypes": excluded_phenotypes,
        "phenotype_features": case.phenotype_features,
        "phenopacket_metadata": case.metadata,
        "unmatched_phenotypes": unmatched_phenotypes,
        "unmatched_excluded_phenotypes": unmatched_excluded,
        "hpo_metadata": hpo_metadata,
        "gene_candidates": gene_candidates,
        "variant_candidates": variant_candidates,
        "sources": {
            "hpo": "PyHPO 4.0.0 / bundled HPO annotations",
            "gtex": "GTEx Portal API v2 / gtex_v10 (only when explicitly requested)",
            "vep": "Ensembl VEP REST API (only when explicitly requested)",
            "phenotype_profile": "User-uploaded Phenopacket-style JSON",
        },
        "unmatched_phenotype_note": None if recognized_phenotypes else "Положительные HPO-признаки не распознаны. Проверьте структуру Phenopacket JSON; отрицательные признаки сами по себе не позволяют ранжировать гены.",
        "variant_count": len(case.variants),
        "variants": [variant.to_dict() for variant in case.variants],
        "source_files": case.source_files,
        "warnings": warnings,
        "weights": ranking_config["weights"],
        "score_interpretation": "HPO-балл используется только для ранжирования вариантов в этом учебном запуске; это не вероятность заболевания и не клиническая классификация.",
        "candidates": [candidate.to_dict() for candidate in candidates],
        "limitations": [
            "ClinVar/gnomAD/VEP не считаются использованными, если соответствующие значения отсутствуют во входных данных или внешняя аннотация не запрашивалась.",
            "Проверка механизма заболевания ограничена моделью наследования и курируемыми примечаниями; функциональный эффект варианта требует транскриптной и экспериментальной оценки.",
            "Гетерозиготный генотип совместим с некоторыми аутосомно-доминантными моделями, но сам по себе не доказывает патогенность.",
            "Синтетический составной генотип, если он используется в учебном наборе, не является геномом реального пациента.",
            "Не найденный кандидат не исключает генетическую причину.",
        ],
    }


def analyze_path(path: Path, output_dir: Path, phenotype_text: str = "") -> list[dict[str, Any]]:
    cases = [load_case(path, phenotype_text)]
    reports = [analyze_case(case) for case in cases]
    write_reports(reports, output_dir)
    return reports
