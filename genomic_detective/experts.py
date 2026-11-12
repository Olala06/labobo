from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import CaseInput, ExpertResult, PhenotypeHit, Variant


PATHOGENIC = {"pathogenic", "likely pathogenic", "pathogenic/likely pathogenic"}
BENIGN = {"benign", "likely benign", "benign/likely benign"}
VUS_MARKERS = {"uncertain significance", "vus", "conflicting interpretations"}


def phenotype_expert(condition: dict[str, Any], hits: list[PhenotypeHit]) -> ExpertResult:
    expected = set(condition.get("phenotypes", []))
    observed = {hit.hpo_id for hit in hits}
    matched = sorted(expected & observed)
    score = len(matched) / len(expected) if expected else 0.0
    label_by_hpo = {hit.hpo_id: hit.label for hit in hits}
    evidence = [f"Совпадение фенотипа: {label_by_hpo.get(hpo, hpo)} ({hpo})" for hpo in matched]
    if not matched:
        evidence.append("Совпадений с курируемыми HPO-признаками из профиля заболевания нет.")
    return ExpertResult(score, evidence, matched_hpo=matched)


def molecular_expert(condition: dict[str, Any], variants: list[Variant]) -> ExpertResult:
    genes = {str(gene).upper() for gene in condition.get("genes", [])}
    matches = [variant for variant in variants if variant.gene and variant.gene.upper() in genes]
    evidence: list[str] = []
    for variant in matches:
        locus = f"{variant.chrom}:{variant.pos}:{variant.ref}>{variant.alt}"
        clin = (variant.clinvar or "").lower().replace("_", " ").strip()
        if any(marker in clin for marker in VUS_MARKERS):
            evidence.append(f"{locus} ({variant.gene}): ClinVar VUS/конфликт — клиническая поддержка не добавлена.")
            continue
        if any(marker in clin for marker in BENIGN):
            evidence.append(f"{locus} ({variant.gene}): ClinVar benign/likely benign — поддержка гипотезы не добавлена.")
            continue
        if any(marker in clin for marker in PATHOGENIC):
            evidence.append(f"{locus} ({variant.gene}): в источнике указана pathogenic-категория ClinVar, но она не засчитывается без проверки точного ALT-аллеля, конкретного заболевания, транскрипта и review status.")
            continue
        if variant.consequence:
            evidence.append(f"{locus} ({variant.gene}): есть аннотация последствия «{variant.consequence}», но она сама по себе не доказывает патогенность.")
        else:
            evidence.append(f"{locus} ({variant.gene}): найден вариант в гене-кандидате, но классификация/последствие не представлены.")
    # No clinical molecular score is granted until allele-condition-transcript evidence
    # has been curated and independently reviewed. Gene overlap is descriptive only.
    score = 0.0
    if not matches:
        evidence.append("В предоставленных вариантах не обнаружен ген из списка генов данного заболевания (или поле гена отсутствует).")
    return ExpertResult(score, evidence, matched_variants=[
        f"{v.chrom}:{v.pos}:{v.ref}>{v.alt} ({v.gene})" for v in matches
    ])


def inheritance_expert(condition: dict[str, Any], variants: list[Variant]) -> ExpertResult:
    mode = str(condition.get("inheritance", "unknown")).upper()
    genes = {str(gene).upper() for gene in condition.get("genes", [])}
    relevant = [v for v in variants if v.gene and v.gene.upper() in genes]
    genotypes = [v.genotype for v in relevant if v.genotype]
    evidence: list[str] = []
    score = 0.0
    if mode in {"AD", "AUTOSOMAL DOMINANT"}:
        evidence.append("В базе указана аутосомно-доминантная модель; семейная сегрегация и de novo статус по одному VCF не устанавливаются.")
        if any(gt in {"0/1", "1/0", "0|1", "1|0", "1/1", "1|1"} for gt in genotypes):
            score = 0.25
            evidence.append("Обнаружен генотип с ALT-аллелем в гене-кандидате; это лишь совместимость с моделью, не доказательство причинности.")
    elif mode in {"AR", "AUTOSOMAL RECESSIVE"}:
        evidence.append("В базе указана аутосомно-рецессивная модель; необходимо подтвердить два причинных аллеля и их фазу (trans).")
        alt_calls = [gt for gt in genotypes if gt and any(token in gt for token in ("1", "2"))]
        if len(alt_calls) >= 2:
            score = 0.15
            evidence.append("В гене найдены как минимум две записи с ALT-генотипом; число записей не доказывает два разных аллеля или trans-фазу.")
    else:
        evidence.append("Модель наследования не указана в курируемой базе; балл наследования не добавлен.")
    if not relevant:
        evidence.append("Нет вариантов в гене заболевания; оценить совместимость генотипа с моделью нельзя.")
    return ExpertResult(score, evidence, matched_variants=[
        f"{v.chrom}:{v.pos}:{v.ref}>{v.alt} ({v.genotype or 'GT неизвестен'})" for v in relevant
    ])


def run_experts(condition: dict[str, Any], case: CaseInput, hits: list[PhenotypeHit]) -> dict[str, ExpertResult]:
    return {
        "phenotype": phenotype_expert(condition, hits),
        "molecular": molecular_expert(condition, case.variants),
        "inheritance": inheritance_expert(condition, case.variants),
    }
