"""GTEx Portal API v2 tissue-expression context.

Queries are serialized, cached locally, and never contribute to the HPO gene score.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://gtexportal.org/api/v2"
DATASET = "gtex_v10"
CACHE_DAYS = 30


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data", payload.get("results", []))
    else:
        data = payload
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


class GTExProvider:
    def __init__(self, cache_path: Path = Path("data/gtex.sqlite"), timeout: int = 25):
        self.cache_path = cache_path
        self.timeout = timeout
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def _request_json(self, path: str, params: dict[str, str]) -> Any:
        query = urllib.parse.urlencode(params)
        url = f"{BASE}/{path}?{query}"
        cache_key = url
        with sqlite3.connect(self.cache_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS gtex_cache (
                cache_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )""")
            row = db.execute(
                "SELECT response_json, fetched_at FROM gtex_cache WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
            if row and time.time() - float(row[1]) < CACHE_DAYS * 86400:
                return json.loads(row[0])

        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Olala06-labobo/0.3 (GTEx public-data lookup)",
        })
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        with sqlite3.connect(self.cache_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO gtex_cache(cache_key,response_json,fetched_at) VALUES(?,?,?)",
                (cache_key, json.dumps(payload, ensure_ascii=False), time.time()),
            )
        return payload

    def _versioned_gene_id(self, symbol: str, ensembl_ids: list[str]) -> str | None:
        # Prefer the GTEx reference mapping; it supplies the exact GENCODE version
        # required by the GTEx V10 expression endpoint.
        query_values = list(dict.fromkeys(ensembl_ids + [symbol]))
        for value in query_values:
            payload = self._request_json("reference/gene", {
                "geneId": value,
                "genomeBuild": "GRCh38/hg38",
                "gencodeVersion": "v39",
                "page": "0",
                "itemsPerPage": "10",
            })
            for record in _records(payload):
                returned_symbol = str(record.get("geneSymbol") or record.get("geneName") or "").upper()
                if returned_symbol and returned_symbol != symbol.upper():
                    continue
                gene_id = record.get("gencodeId") or record.get("gencode_id")
                if gene_id and str(gene_id).startswith("ENSG"):
                    return str(gene_id)
        return None

    def expression_for_gene(self, symbol: str, ensembl_ids: list[str] | None = None) -> dict[str, Any]:
        ensembl_ids = [str(value).split(".")[0] for value in (ensembl_ids or [])
                       if str(value).startswith("ENSG")]
        ensembl_ids = list(dict.fromkeys(ensembl_ids))
        versioned = self._versioned_gene_id(symbol, ensembl_ids)
        if not versioned:
            return {"status": "unavailable", "reason": "GTEx не сопоставил gene symbol с GENCODE ID."}

        payload = self._request_json("expression/medianGeneExpression", {
            "gencodeId": versioned,
            "datasetId": DATASET,
            "page": "0",
            "itemsPerPage": "1000",
        })
        rows = []
        for record in _records(payload):
            tissue = (record.get("tissueSiteDetail") or record.get("tissueSiteDetailId")
                      or record.get("tissueSiteOntologyId"))
            median = record.get("median")
            try:
                median_value = float(median)
            except (TypeError, ValueError):
                continue
            if tissue:
                rows.append({"tissue": str(tissue), "median_tpm": median_value})
        rows.sort(key=lambda row: row["median_tpm"], reverse=True)
        if not rows:
            return {"status": "unavailable", "gencode_id": versioned,
                    "reason": "Для гена не получены значения median expression."}
        return {
            "status": "available",
            "dataset": DATASET,
            "gencode_id": versioned,
            "unit": "median normalized expression (TPM scale as returned by GTEx)",
            "top_tissues": rows[:8],
            "source_url": "https://gtexportal.org/home/gene/" + urllib.parse.quote(versioned, safe=""),
        }

    def annotate_gene_candidates(self, candidates: list[dict[str, Any]], limit: int = 20) -> list[str]:
        warnings = []
        for candidate in candidates[:max(0, min(limit, 20))]:
            try:
                candidate["gtex"] = self.expression_for_gene(
                    candidate["gene"], candidate.get("ensembl_gene_ids", []))
            except (OSError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                candidate["gtex"] = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
                warnings.append(f"GTEx для {candidate['gene']} недоступен; HPO-оценка не изменена.")
        return warnings
