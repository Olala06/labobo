from __future__ import annotations

import csv
import gzip
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable

from .knowledge import load_knowledge
from .models import CaseInput, PhenotypeHit, Variant


def _decode(name: str, raw: bytes) -> str:
    if name.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
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


def _phenotype_text_from_file(name: str, raw: bytes) -> str:
    text = _decode(name, raw)
    if name.lower().endswith(".json"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                values = payload.get("phenotypes") or payload.get("hpo_terms") or payload.get("terms") or []
            else:
                values = payload
            if isinstance(values, list):
                return " ".join(
                    str(item.get("hpo_id") or item.get("id") or item.get("name") or item)
                    if isinstance(item, dict) else str(item)
                    for item in values
                )
        except (json.JSONDecodeError, TypeError):
            pass
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
    sources: list[str] = []
    for name, raw in entries:
        lower = name.lower()
        base = Path(lower).name
        if base.endswith((".vcf", ".vcf.gz")):
            parsed, issues = parse_vcf(_decode(name, raw))
            variants.extend(parsed)
            warnings.extend(issues)
            sources.append(name)
        elif base.endswith(".tsv") and any(token in base for token in ("variant", "object", "genome", "vcf")):
            parsed, issues = parse_tsv(_decode(name, raw))
            variants.extend(parsed)
            warnings.extend(issues)
            sources.append(name)
        elif any(token in base for token in ("phenotype", "phenotypes", "hpo")) and base.endswith((".txt", ".tsv", ".json", ".hpo")):
            phenotype_parts.append(_phenotype_text_from_file(name, raw))
            sources.append(name)
    if not variants:
        warnings.append("No VCF/variant TSV records were found in the supplied files.")
    return CaseInput(case_name, variants, "\n".join(phenotype_parts), sources, warnings)


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
