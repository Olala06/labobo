"""HPO-backed phenotype parsing and gene prioritization using PyHPO.

The PyHPO wheel is fetched only when needed in the portable Windows runtime.
Its SHA-256 is pinned to the official PyPI release artifact before extraction.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
import shutil
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

PYHPO_VERSION = "4.0.0"
PYHPO_WHEEL_SHA256 = "cfa39f1416b8f29a206156d43ec36ce532873a778a11fcfdfb8d46386b9ab0d6"
PYPI_JSON = "https://pypi.org/pypi/pyhpo/4.0.0/json"
_ENGINE: "HPOEngine | None" = None
_ENGINE_LOCK = threading.Lock()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_pyhpo():
    try:
        return importlib.import_module("pyhpo")
    except ImportError:
        pass

    # The official Python embeddable distribution has no pip. Install the pure
    # Python wheel into a project-local directory without altering the machine.
    destination = _project_root() / ".runtime" / "packages" / f"pyhpo-{PYHPO_VERSION}"
    package_dir = destination / "pyhpo"
    if not package_dir.is_dir():
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(PYPI_JSON, headers={"User-Agent": "labobo-genomic-detective/0.3"})
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.loads(response.read().decode("utf-8"))
        wheel_meta = next((item for item in release.get("urls", [])
                           if item.get("filename") == f"pyhpo-{PYHPO_VERSION}-py3-none-any.whl"), None)
        if not wheel_meta or wheel_meta.get("digests", {}).get("sha256") != PYHPO_WHEEL_SHA256:
            raise RuntimeError("Не удалось подтвердить официальный архив PyHPO по SHA-256.")
        wheel_request = urllib.request.Request(wheel_meta["url"],
            headers={"User-Agent": "labobo-genomic-detective/0.3"})
        with urllib.request.urlopen(wheel_request, timeout=90) as response:
            wheel = response.read()
        if hashlib.sha256(wheel).hexdigest() != PYHPO_WHEEL_SHA256:
            raise RuntimeError("SHA-256 архива PyHPO не совпадает; установка отменена.")
        staging = destination.with_name(destination.name + ".tmp")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(wheel)) as archive:
                root = staging.resolve()
                for item in archive.infolist():
                    target = (staging / item.filename).resolve()
                    if target != root and root not in target.parents:
                        raise RuntimeError("В архиве PyHPO найден небезопасный путь.")
                archive.extractall(staging)
            if not (staging / "pyhpo").is_dir():
                raise RuntimeError("Официальный wheel PyHPO не содержит пакет pyhpo.")
            if destination.exists():
                shutil.rmtree(destination)
            staging.replace(destination)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    sys.path.insert(0, str(destination))
    importlib.invalidate_caches()
    return importlib.import_module("pyhpo")


def _term_id_as_int(term: Any) -> int:
    return int(str(term.id).split(":")[-1])


class HPOEngine:
    """Thin application adapter over PyHPO Ontology, Gene and HPOSet."""

    def __init__(self) -> None:
        _load_pyhpo()
        from pyhpo import Ontology
        from pyhpo.set import HPOSet
        from pyhpo.annotations import Gene

        self.ontology = Ontology()
        self.HPOSet = HPOSet
        self.Gene = Gene

    @staticmethod
    def _term_payload(term: Any) -> dict[str, str]:
        return {"id": str(term.id), "label": str(term.name)}

    def search(self, query: str, limit: int = 20) -> list[dict[str, str]]:
        query = query.strip()
        if len(query) < 2:
            return []
        terms = list(self.ontology.search(query))
        folded = query.casefold()
        terms.sort(key=lambda term: (
            str(term.name).casefold() != folded,
            not str(term.name).casefold().startswith(folded),
            str(term.id),
        ))
        result = []
        seen = set()
        for term in terms:
            if getattr(term, "is_obsolete", False):
                continue
            if term.id not in seen:
                result.append(self._term_payload(term))
                seen.add(term.id)
            if len(result) >= min(max(limit, 1), 30):
                break
        return result

    def resolve(self, phenotype_text: str) -> dict[str, Any]:
        tokens = re.findall(r"HP:?\\d{7}", phenotype_text, flags=re.IGNORECASE)
        chunks = re.split(r"[\\n,;]+", phenotype_text)
        chunks = [part.strip(" \\t .") for part in chunks if part.strip(" \\t .")]
        queries = list(dict.fromkeys(tokens + chunks))
        terms = []
        unmatched = []
        seen = set()
        for query in queries[:250]:
            try:
                term = self.ontology.get_hpo_object(query.replace("HP", "HP", 1))
            except (RuntimeError, TypeError, ValueError, KeyError):
                # PyHPO's search includes ontology labels and synonyms. Only accept
                # a unique exact label/synonym match to avoid guessing from prose.
                matches = list(self.ontology.search(query))
                exact = [item for item in matches if
                         str(item.name).casefold() == query.casefold()
                         or any(str(alias).casefold() == query.casefold()
                                for alias in getattr(item, "synonym", []))]
                term = exact[0] if len(exact) == 1 else None
            if term is None or getattr(term, "is_obsolete", False):
                if query not in unmatched:
                    unmatched.append(query)
                continue
            if term.id not in seen:
                terms.append(term)
                seen.add(term.id)

        return {
            "terms": terms,
            "recognized": [self._term_payload(term) for term in terms],
            "unmatched": unmatched,
        }

    def rank_genes(self, variants: list[Any], phenotype_terms: list[Any], limit: int = 100) -> list[dict[str, Any]]:
        if not variants or not phenotype_terms:
            return []
        observed = self.HPOSet(phenotype_terms).child_nodes()
        symbols: dict[str, list[Any]] = {}
        for variant in variants:
            symbol = (getattr(variant, "gene", None)
                      or getattr(variant, "info", {}).get("VEP_TRANSCRIPT", {}).get("gene_symbol"))
            if symbol:
                symbols.setdefault(str(symbol).upper(), []).append(variant)

        candidates = []
        for symbol, gene_variants in symbols.items():
            try:
                gene = self.Gene.get(symbol)
                annotated_set = gene.hpo_set()
                if not annotated_set:
                    continue
                similarity = float(observed.similarity(
                    annotated_set, kind="gene", combine="funSimAvg"))
            except (KeyError, ValueError, RuntimeError, AttributeError, TypeError):
                continue
            if not 0.0 <= similarity <= 1.0:
                continue
            direct_ids = set(getattr(gene, "hpo", set()))
            matched = []
            for term in phenotype_terms:
                if _term_id_as_int(term) in direct_ids:
                    matched.append(self._term_payload(term))
            transcript_ids = sorted({
                str(v.info.get("VEP_TRANSCRIPT", {}).get("gene_id"))
                for v in gene_variants
                if v.info.get("VEP_TRANSCRIPT", {}).get("gene_id")
            })
            candidates.append({
                "gene": symbol,
                "hpo_similarity": round(similarity, 4),
                "hpo_similarity_percent": round(similarity * 100, 1),
                "similarity_method": "PyHPO funSimAvg / gene information content",
                "directly_matched_hpo": matched,
                "annotated_hpo_terms": len(annotated_set),
                "ensembl_gene_ids": transcript_ids,
                "variants": [{
                    "locus": f"{v.chrom}:{v.pos}:{v.ref}>{v.alt}",
                    "consequence": v.consequence,
                    "genotype": v.genotype,
                } for v in gene_variants],
                "gtex": None,
            })
        return sorted(candidates, key=lambda item: (
            item["hpo_similarity"], len(item["directly_matched_hpo"])
        ), reverse=True)[:limit]


def get_hpo_engine() -> HPOEngine:
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = HPOEngine()
    return _ENGINE
