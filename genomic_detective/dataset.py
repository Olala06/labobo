from __future__ import annotations

import csv
import gzip
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .models import CaseInput, PhenotypeHit, Variant


def _decode(name: str, raw: bytes, max_bytes: int = 150 * 1024 * 1024) -> str:
    if name.lower().endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"Expanded gzip file exceeds the {max_bytes // (1024 * 1024)} MB safety limit.")
    if len(raw) > max_bytes:
        raise ValueError(f"File exceeds the {max_bytes // (1024 * 1024)} MB safety limit.")
    return raw.decode("utf-8-sig", errors="replace")


def _gene_from_info(info: dict[str, str | bool], csq_format: list[str]) -> tuple[str | None, str | None, str | None]:
    gene = info.get("SYMBOL") or info.get("GENE") or info.get("Gene") or info.get("GENEINFO")
    consequence = info.get("Consequence")
    clinvar = info.get("CLNSIG") or info.get("CLIN_SIG")
    if isinstance(info.get("CSQ"), str) and csq_format:
        first = str(info["CSQ"]).split(",")[0].split("|")
        values = dict(zip(csq_format, first))
        gene = gene or values.get("SYMBOL") or values.get("Gene")
        consequence = consequence or values.get("Consequence")
        clinvar = clinvar or values.get("CLIN_SIG")
    if isinstance(info.get("ANN"), str):
        ann = str(info["ANN"]).split(",")[0].split("|")
        if len(ann) > 3:
            consequence = consequence or ann[1]
            gene = gene or ann[3]
    if isinstance(gene, str) and ":" in gene and gene.split(":", 1)[0].isupper():
        gene = gene.split(":", 1)[0]
    return (str(gene).split(";")[0] if gene else None,
            str(consequence) if consequence else None,
            str(clinvar) if clinvar else None)


def parse_vcf(text: str) -> tuple[list[Variant], list[str]]:
    variants: list[Variant] = []
    warnings: list[str] = []
    csq_format: list[str] = []
    sample_index: int | None = None
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.startswith("##INFO=<ID=CSQ"):
            match = re.search(r"Format: ([^\">]+)", line)
            if match:
                csq_format = match.group(1).strip().split("|")
            continue
        if not line or line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            sample_index = 9 if len(line.split("\t")) > 9 else None
            continue
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            warnings.append(f"VCF line {line_no}: expected at least 8 tab-separated columns")
            continue
        chrom, pos, variant_id, ref, alt, qual, filt, raw_info = cols[:8]
        try:
            position = int(pos)
        except ValueError:
            warnings.append(f"VCF line {line_no}: invalid position {pos!r}")
            continue
        info: dict[str, str | bool] = {}
        for field in raw_info.split(";"):
            if "=" in field:
                key, value = field.split("=", 1)
                info[key] = value
            elif field:
                info[field] = True
        gene, consequence, clinvar = _gene_from_info(info, csq_format)
        genotype = None
        if sample_index is not None and len(cols) > sample_index:
            format_keys = cols[8].split(":") if len(cols) > 8 else []
            sample_values = cols[sample_index].split(":")
            if "GT" in format_keys:
                idx = format_keys.index("GT")
                genotype = sample_values[idx] if idx < len(sample_values) else None
        variants.append(Variant(
            chrom=chrom, pos=position, ref=ref, alt=alt, gene=gene,
            consequence=consequence, clinvar=clinvar, genotype=genotype,
            variant_id=None if variant_id == "." else variant_id,
            quality=None if qual == "." else qual,
            filter=None if filt == "." else filt, info=dict(info),
        ))
    return variants, warnings


def parse_tsv(text: str) -> tuple[list[Variant], list[str]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames:
        return [], ["TSV file has no header row"]
    normalized = {name.lower().strip(): name for name in reader.fieldnames}

    def value(row: dict[str, str], *names: str) -> str | None:
        for name in names:
            column = normalized.get(name)
            if column and row.get(column):
                return row[column].strip()
        return None

    variants: list[Variant] = []
    warnings: list[str] = []
    for line_no, row in enumerate(reader, 2):
        pos = value(row, "pos", "position", "start")
        try:
            position = int(pos or "")
        except ValueError:
            warnings.append(f"TSV line {line_no}: missing or invalid position")
            continue
        variants.append(Variant(
            chrom=value(row, "chrom", "chr", "chromosome") or "?",
            pos=position, ref=value(row, "ref", "reference") or "N",
            alt=value(row, "alt", "alternate") or "N",
            gene=value(row, "gene", "symbol", "genesymbol"),
            consequence=value(row, "consequence", "effect", "annotation"),
            clinvar=value(row, "clinvar", "clinical_significance", "clnsig"),
            genotype=value(row, "genotype", "gt"),
            variant_id=value(row, "id", "variant_id"),
            info={},
        ))
    return variants, warnings


def _as_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("name") or value.get("id") or "")
    return str(value or "")


def parse_phenopacket(text: str) -> dict[str, Any]:
    """Read Phenopacket-style JSON while retaining positive and excluded HPO features."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Файл фенотипов должен быть корректным JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Ожидается JSON-объект Phenopacket, а не массив или скаляр.")

    features = (
        payload.get("phenotypicFeatures")
        or payload.get("phenotypic_features")
        or payload.get("phenotypes")
        or payload.get("hpo_terms")
        or payload.get("terms")
    )
    if not isinstance(features, list):
        raise ValueError("В JSON не найден список phenotypicFeatures / phenotypes.")

    positive: list[str] = []
    excluded: list[str] = []
    normalized_features: list[dict[str, Any]] = []
    seen: set[tuple[str, bool]] = set()
    for item in features:
        if isinstance(item, (str, int)):
            term = item
            is_excluded = False
        elif isinstance(item, dict):
            term = item.get("type") or item.get("term") or item.get("phenotype") or item
            excluded_value = item.get("excluded", False)
            is_excluded = (
                excluded_value is True
                or str(excluded_value).strip().lower() in {"true", "1", "yes"}
            )
        else:
            continue

        hpo_id = ""
        label = ""
        if isinstance(term, dict):
            hpo_id = str(term.get("id") or term.get("hpo_id") or term.get("hpoId") or "")
            label = str(term.get("label") or term.get("name") or "")
        else:
            token = str(term or "").strip()
            if re.fullmatch(r"HP:?\d{7}", token, flags=re.IGNORECASE):
                hpo_id = token if ":" in token else f"HP:{token[2:]}"
            else:
                label = token
        hpo_id = hpo_id.strip()
        if not hpo_id and not label:
            continue
        value = hpo_id or label
        key = (value.casefold(), is_excluded)
        if key in seen:
            continue
        seen.add(key)
        target = excluded if is_excluded else positive
        target.append(value)
        normalized_features.append({
            "id": hpo_id or None,
            "label": label or hpo_id or value,
            "excluded": is_excluded,
        })

    if not normalized_features:
        raise ValueError("В файле не найдено ни одного распознаваемого HPO-признака.")

    subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
    packet_id = str(payload.get("id") or payload.get("case_id") or subject.get("id") or "")
    diseases = []
    for disease in payload.get("diseases", []) if isinstance(payload.get("diseases"), list) else []:
        if not isinstance(disease, dict):
            continue
        term = disease.get("term") or disease.get("disease") or disease
        if isinstance(term, dict):
            diseases.append({
                "id": term.get("id"),
                "label": term.get("label") or term.get("name") or term.get("id"),
            })

    return {
        "positive_text": " ".join(positive),
        "excluded_text": " ".join(excluded),
        "features": normalized_features,
        "metadata": {
            "phenopacket_id": packet_id or None,
            "subject_id": subject.get("id"),
            "diseases": diseases,
            "schema_version": payload.get("schemaVersion") or payload.get("schema_version"),
        },
    }


def _phenotype_text_from_file(name: str, raw: bytes) -> str:
    text = _decode(name, raw)
    if name.lower().endswith(".json"):
        profile = parse_phenopacket(text)
        return profile["positive_text"] + " " + profile["excluded_text"]
    return text


def parse_phenotypes(text: str, knowledge: dict) -> list[PhenotypeHit]:
    normalized = re.sub(r"[^a-zа-яё0-9:]+", " ", text.lower())
    hits: list[PhenotypeHit] = []
    seen: set[str] = set()
    for item in knowledge["phenotype_terms"]:
        hpo_id = str(item["hpo"])
        if hpo_id in seen:
            continue
        for alias in [item["label"], *item.get("aliases", [])]:
            term = str(alias).lower()
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized):
                hits.append(PhenotypeHit(str(item["label"]), hpo_id, str(alias)))
                seen.add(hpo_id)
                break
        if hpo_id not in seen and hpo_id.lower() in normalized:
            hits.append(PhenotypeHit(str(item["label"]), hpo_id, hpo_id))
            seen.add(hpo_id)
    return hits


def parse_case_files(files: Iterable[tuple[str, bytes]], case_name: str, phenotype_text: str = "") -> CaseInput:
    entries = list(files)
    variants: list[Variant] = []
    warnings: list[str] = []
    phenotype_parts = [phenotype_text] if phenotype_text.strip() else []
    excluded_parts: list[str] = []
    phenotype_features: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    sources: list[str] = []
    for name, raw in entries:
        lower = name.lower()
        base = Path(lower).name
        if base.endswith((".vcf", ".vcf.gz")):
            parsed, issues = parse_vcf(_decode(name, raw))
            variants.extend(parsed)
            warnings.extend(issues)
            sources.append(name)
        elif base.endswith(".json"):
            profile = parse_phenopacket(_decode(name, raw))
            if phenotype_features:
                raise ValueError("Загрузите только один JSON-файл фенотипов.")
            phenotype_parts.append(profile["positive_text"])
            excluded_parts.append(profile["excluded_text"])
            phenotype_features.extend(profile["features"])
            metadata.update(profile["metadata"])
            sources.append(name)
        elif base.endswith(".tsv") and any(token in base for token in ("phenotype", "phenotypes", "hpo")):
            phenotype_parts.append(_phenotype_text_from_file(name, raw))
            sources.append(name)
        elif base.endswith(".tsv"):
            parsed, issues = parse_tsv(_decode(name, raw))
            if parsed:
                variants.extend(parsed)
                warnings.extend(issues)
                sources.append(name)
            else:
                warnings.extend(issues)
        elif any(token in base for token in ("phenotype", "phenotypes", "hpo")) and base.endswith((".txt", ".hpo")):
            phenotype_parts.append(_phenotype_text_from_file(name, raw))
            sources.append(name)
    if not variants:
        warnings.append("No VCF/variant TSV records were found in the supplied files.")
    if not phenotype_features and not any(item.strip() for item in phenotype_parts):
        warnings.append("No phenotype terms were found in the supplied files.")
    if metadata.get("phenopacket_id"):
        case_name = str(metadata["phenopacket_id"])
    return CaseInput(
        case_name, variants, "\n".join(part for part in phenotype_parts if part),
        sources, warnings, "\n".join(part for part in excluded_parts if part),
        phenotype_features, metadata,
    )


def load_case(path: Path, phenotype_text: str = "") -> CaseInput:
    if path.is_dir():
        files = [(str(item.relative_to(path)), item.read_bytes()) for item in path.rglob("*") if item.is_file()]
        return parse_case_files(files, path.name, phenotype_text)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            files = [(item.filename, archive.read(item)) for item in archive.infolist() if not item.is_dir()]
        return parse_case_files(files, path.stem, phenotype_text)
    return parse_case_files([(path.name, path.read_bytes())], path.stem, phenotype_text)


def uploaded_case(filename: str, content: bytes, phenotype_text: str = "") -> CaseInput:
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = [(item.filename, archive.read(item)) for item in archive.infolist() if not item.is_dir()]
        return parse_case_files(files, Path(filename).stem, phenotype_text)
    return parse_case_files([(filename, content)], Path(filename).stem, phenotype_text)
