from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import CaseInput, Variant

VEP_URL = "https://rest.ensembl.org/vep/human/region?content-type=application/json"


def _vep_input(variant: Variant) -> str | None:
    chrom = str(variant.chrom).removeprefix("chr").removeprefix("CHR")
    ref = variant.ref.upper()
    alt = variant.alt.upper()
    if not chrom or not ref or not alt or "," in alt or alt.startswith("<") or alt == "*":
        return None
    end = variant.pos + len(ref) - 1
    return f"{chrom} {variant.pos} . {ref} {alt} . . ."


def _normalize_input(value: str) -> str:
    return " ".join(value.split())


def _post_batch(inputs: list[str], timeout: int = 60) -> list[dict[str, Any]]:
    payload = json.dumps({"variants": inputs}).encode("utf-8")
    request = urllib.request.Request(
        VEP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Olala06-GenomicDetective/0.2",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Ensembl VEP returned an unexpected response shape")
    return [item for item in data if isinstance(item, dict)]


def _select_transcript(annotation: dict[str, Any], alt: str) -> dict[str, Any] | None:
    consequences = annotation.get("transcript_consequences", [])
    if not isinstance(consequences, list):
        return None
    matching = [
        item for item in consequences
        if isinstance(item, dict) and str(item.get("variant_allele", "")).upper() == alt.upper()
    ]
    pool = matching or [item for item in consequences if isinstance(item, dict)]
    if not pool:
        return None

    def priority(item: dict[str, Any]) -> tuple[int, int, int]:
        return (
            0 if item.get("mane_select") else 1,
            0 if item.get("canonical") else 1,
            0 if item.get("biotype") == "protein_coding" else 1,
        )
    return sorted(pool, key=priority)[0]


def _apply_annotation(variant: Variant, annotation: dict[str, Any]) -> None:
    transcript = _select_transcript(annotation, variant.alt)
    if transcript:
        variant.gene = transcript.get("gene_symbol") or variant.gene
        terms = transcript.get("consequence_terms") or []
        if terms:
            variant.consequence = "&".join(str(term) for term in terms)
        variant.info["VEP_TRANSCRIPT"] = {
            "transcript_id": transcript.get("transcript_id"),
            "gene_id": transcript.get("gene_id"),
            "gene_symbol": transcript.get("gene_symbol"),
            "biotype": transcript.get("biotype"),
            "mane_select": transcript.get("mane_select"),
            "canonical": transcript.get("canonical"),
            "consequence_terms": transcript.get("consequence_terms", []),
            "impact": transcript.get("impact"),
        }
    variant.info["VEP"] = {
        "assembly_name": annotation.get("assembly_name"),
        "most_severe_consequence": annotation.get("most_severe_consequence"),
        "allele_string": annotation.get("allele_string"),
        "input": annotation.get("input"),
        "id": annotation.get("id"),
    }
    if not variant.consequence and annotation.get("most_severe_consequence"):
        variant.consequence = str(annotation["most_severe_consequence"])


def annotate_case(
    case: CaseInput,
    cache_path: Path = Path("data/ensembl-vep.sqlite"),
    batch_size: int = 200,
) -> dict[str, int]:
    if not 1 <= batch_size <= 200:
        raise ValueError("VEP batch size must be between 1 and 200")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached_count = annotated_count = failed_count = skipped_count = 0
    pending: dict[str, list[Variant]] = {}
    with sqlite3.connect(cache_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS vep_cache (
                assembly TEXT NOT NULL,
                input_key TEXT NOT NULL,
                response_json TEXT NOT NULL,
                PRIMARY KEY (assembly, input_key)
            )
        """)
        for variant in case.variants:
            request_input = _vep_input(variant)
            if request_input is None:
                skipped_count += 1
                case.warnings.append(
                    f"VEP skipped unsupported allele at {variant.chrom}:{variant.pos} ({variant.ref}>{variant.alt})."
                )
                continue
            key = _normalize_input(request_input)
            row = connection.execute(
                "SELECT response_json FROM vep_cache WHERE assembly=? AND input_key=?",
                ("GRCh38", key),
            ).fetchone()
            if row:
                annotation = json.loads(row[0])
                _apply_annotation(variant, annotation)
                cached_count += 1
            else:
                pending.setdefault(key, []).append(variant)

        keys = list(pending)
        for offset in range(0, len(keys), batch_size):
            batch_keys = keys[offset:offset + batch_size]
            try:
                response = _post_batch(batch_keys)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                failed_count += len(batch_keys)
                case.warnings.append(
                    f"Ensembl VEP batch {offset // batch_size + 1} failed: {type(exc).__name__}: {exc}"
                )
                continue

            by_input = {
                _normalize_input(str(item.get("input", ""))): item
                for item in response if item.get("input")
            }
            if not by_input and len(response) == len(batch_keys):
                by_input = dict(zip(batch_keys, response))
            for key in batch_keys:
                annotation = by_input.get(key)
                if annotation is None:
                    failed_count += len(pending[key])
                    case.warnings.append(f"Ensembl VEP returned no matching annotation for {key}.")
                    continue
                connection.execute(
                    "INSERT OR REPLACE INTO vep_cache(assembly,input_key,response_json) VALUES(?,?,?)",
                    ("GRCh38", key, json.dumps(annotation, ensure_ascii=False)),
                )
                for variant in pending[key]:
                    _apply_annotation(variant, annotation)
                    annotated_count += 1
        connection.commit()

    return {
        "cached": cached_count,
        "annotated": annotated_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }
