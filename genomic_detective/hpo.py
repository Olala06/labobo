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
import sysconfig
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


DEPENDENCY_WHEELS = [
    ("annotated-types", "0.7.0"),
    ("typing-extensions", "4.14.1"),
    ("typing-inspection", "0.4.2"),
    ("pydantic-core", "2.46.4"),
    ("pydantic", "2.13.4"),
]


def _wheel_filename(files: list[dict[str, Any]], package: str) -> dict[str, Any]:
    wheels = [item for item in files if item.get("filename", "").endswith(".whl")]
    if package != "pydantic-core":
        exact_suffix = "-py3-none-any.whl"
        match = next((item for item in wheels if item["filename"].endswith(exact_suffix)), None)
        if match:
            return match
        raise RuntimeError(f"PyPI не опубликовал совместимый универсальный wheel для {package}.")

    version = f"cp{sys.version_info.major}{sys.version_info.minor}"
    platform = sysconfig.get_platform().lower()
    if platform.startswith("win-"):
        arch = platform.split("-", 1)[1].replace("-", "_")
        suffix = f"-{version}-{version}-win_{arch}.whl"
        match = next((item for item in wheels if item["filename"].endswith(suffix)), None)
    elif platform.startswith("linux-"):
        arch = platform.split("-", 1)[1]
        suffix = f"_{arch}.whl"
        candidates = [
            item for item in wheels
            if f"-{version}-{version}-manylinux" in item["filename"]
            and item["filename"].endswith(suffix)
        ]
        # Prefer the oldest glibc baseline for the widest Linux compatibility.
        candidates.sort(key=lambda item: (
            0 if "manylinux_2_17" in item["filename"] else
            1 if "manylinux2014" in item["filename"] else 2,
            item["filename"],
        ))
        match = candidates[0] if candidates else None
    elif platform.startswith("macosx-"):
        arch = platform.rsplit("-", 1)[-1].replace("-", "_")
        candidates = [
            item for item in wheels
            if f"-{version}-{version}-macosx_" in item["filename"]
            and item["filename"].endswith(f"_{arch}.whl")
        ]
        match = candidates[0] if candidates else None
    else:
        match = None

    if not match:
        raise RuntimeError(
            f"Для pydantic-core нет wheel под Python {sys.version_info.major}.{sys.version_info.minor} "
            f"и платформу {platform}. Установите зависимости командой pip install pyhpo=={PYHPO_VERSION}."
        )
    return match


def _fetch_wheel(package: str, version: str, staging: Path) -> None:
    api_url = f"https://pypi.org/pypi/{package}/{version}/json"
    request = urllib.request.Request(api_url, headers={
        "User-Agent": "labobo-genomic-detective/0.3",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=45) as response:
        release = json.loads(response.read().decode("utf-8"))

    if package == "pyhpo":
        wheel_meta = next((item for item in release.get("urls", [])
                           if item.get("filename") == f"pyhpo-{version}-py3-none-any.whl"), None)
        expected_digest = PYHPO_WHEEL_SHA256
    else:
        wheel_meta = _wheel_filename(release.get("urls", []), package)
        expected_digest = str(wheel_meta.get("digests", {}).get("sha256", ""))

    if not wheel_meta or not expected_digest or wheel_meta.get("digests", {}).get("sha256") != expected_digest:
        raise RuntimeError(f"Не удалось подтвердить официальный wheel {package}=={version} по SHA-256.")

    wheel_request = urllib.request.Request(wheel_meta["url"], headers={
        "User-Agent": "labobo-genomic-detective/0.3",
    })
    with urllib.request.urlopen(wheel_request, timeout=120) as response:
        wheel = response.read()
    if hashlib.sha256(wheel).hexdigest() != expected_digest:
        raise RuntimeError(f"SHA-256 wheel {package}=={version} не совпадает; установка отменена.")

    from io import BytesIO
    with zipfile.ZipFile(BytesIO(wheel)) as archive:
        root = staging.resolve()
        for item in archive.infolist():
            target = (staging / item.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"В wheel {package} найден небезопасный путь.")
        archive.extractall(staging)


def _load_pyhpo():
    try:
        return importlib.import_module("pyhpo")
    except ImportError:
        pass

    # The official Python embeddable distribution has no pip. Install wheels
    # into one project-local directory without touching the machine-wide Python.
    destination = _project_root() / ".runtime" / "packages" / f"pyhpo-{PYHPO_VERSION}"
    complete_marker = destination / ".installation-complete"
    if not complete_marker.is_file():
        staging = destination.with_name(destination.name + ".tmp")
        if staging.exists():
            shutil.rmtree(staging)
        if destination.exists():
            shutil.rmtree(destination)
        staging.mkdir(parents=True)
        try:
            for package, version in DEPENDENCY_WHEELS:
                _fetch_wheel(package, version, staging)
            _fetch_wheel("pyhpo", PYHPO_VERSION, staging)
            if not (staging / "pyhpo").is_dir() or not (staging / "pydantic").is_dir():
                raise RuntimeError("В загруженных wheels отсутствуют модули PyHPO или Pydantic.")
            (staging / ".installation-complete").write_text(
                json.dumps({
                    "pyhpo": PYHPO_VERSION,
                    "dependencies": dict(DEPENDENCY_WHEELS),
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                    "platform": sysconfig.get_platform(),
                }, indent=2),
                encoding="utf-8",
            )
            staging.replace(destination)
        except Exception:
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
        tokens = re.findall(r"HP:?\d{7}", phenotype_text, flags=re.IGNORECASE)
        # Remove extracted HPO IDs so a whitespace-separated list is not one unmatched phrase.
        remainder = re.sub(r"HP:?\d{7}", "", phenotype_text, flags=re.IGNORECASE)
        chunks = re.split(r"[\n,;]+", remainder)
        chunks = [part.strip() for part in chunks if part.strip()]
        chunks = [part.strip(" \t .") for part in chunks if part.strip(" \t .")]
        queries = list(dict.fromkeys(tokens + chunks))
        terms = []
        unmatched = []
        seen = set()
        for query in queries[:250]:
            try:
                normalized_query = (f"HP:{query[2:]}" if re.fullmatch(r"HP\d{7}", query, re.IGNORECASE) else query)
                term = self.ontology.get_hpo_object(normalized_query)
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

    def rank_genes(
        self,
        variants: list[Any],
        phenotype_terms: list[Any],
        excluded_terms: list[Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not variants or not phenotype_terms:
            return []
        excluded_terms = excluded_terms or []
        observed = self.HPOSet.from_queries([str(term.id) for term in phenotype_terms]).child_nodes()
        excluded_by_id = {str(term.id): term for term in excluded_terms}
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
            direct_ids = {str(term.id) for term in annotated_set}
            matched = [
                self._term_payload(term) for term in phenotype_terms
                if str(term.id) in direct_ids
            ]
            # Exclusion conflicts are deliberately conservative: only an exact
            # HPO annotation match is flagged. Missing annotations are not treated
            # as evidence that a feature is absent.
            conflicts = [
                self._term_payload(term) for term in excluded_terms
                if str(term.id) in direct_ids
            ]
            conflict_fraction = len(conflicts) / max(1, len(excluded_terms))
            exclusion_penalty = min(0.30, 0.30 * conflict_fraction)
            adjusted = max(0.0, similarity * (1.0 - exclusion_penalty))
            transcript_ids = sorted({
                str(v.info.get("VEP_TRANSCRIPT", {}).get("gene_id"))
                for v in gene_variants
                if v.info.get("VEP_TRANSCRIPT", {}).get("gene_id")
            })
            candidates.append({
                "gene": symbol,
                "hpo_similarity": round(similarity, 4),
                "hpo_similarity_percent": round(similarity * 100, 1),
                "adjusted_hpo_score": round(adjusted, 4),
                "adjusted_hpo_score_percent": round(adjusted * 100, 1),
                "exclusion_penalty": round(exclusion_penalty, 4),
                "similarity_method": "PyHPO funSimAvg / gene information content",
                "directly_matched_hpo": matched,
                "excluded_conflicts": conflicts,
                "annotated_hpo_terms": len(annotated_set),
                "ensembl_gene_ids": transcript_ids,
                "variants": [{
                    "locus": f"{v.chrom}:{v.pos}:{v.ref}>{v.alt}",
                    "variant": f"chr{str(v.chrom).removeprefix('chr')}:{v.pos}:{v.ref}:{v.alt}",
                    "consequence": v.consequence,
                    "genotype": v.genotype,
                } for v in gene_variants],
                "gtex": None,
            })
        return sorted(candidates, key=lambda item: (
            item["adjusted_hpo_score"], item["hpo_similarity"],
            len(item["directly_matched_hpo"])
        ), reverse=True)[:limit]


def get_hpo_engine() -> HPOEngine:
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = HPOEngine()
    return _ENGINE
