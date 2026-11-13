from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Variant:
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str | None = None
    consequence: str | None = None
    clinvar: str | None = None
    genotype: str | None = None
    variant_id: str | None = None
    quality: str | None = None
    filter: str | None = None
    info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhenotypeHit:
    label: str
    hpo_id: str
    matched_text: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ExpertResult:
    score: float
    evidence: list[str] = field(default_factory=list)
    matched_hpo: list[str] = field(default_factory=list)
    matched_variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseInput:
    name: str
    variants: list[Variant]
    phenotype_text: str
    source_files: list[str]
    warnings: list[str] = field(default_factory=list)
    excluded_phenotype_text: str = ""
    phenotype_features: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    condition_id: str
    name: str
    genes: list[str]
    inheritance: str
    score: float
    status: str
    experts: dict[str, ExpertResult]
    sources: list[dict[str, str]]
    explanation: list[str]
    mechanism: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "name": self.name,
            "genes": self.genes,
            "inheritance": self.inheritance,
            "score": round(self.score, 4),
            "score_0_to_100": round(self.score * 100, 1),
            "status": self.status,
            "experts": {key: value.to_dict() for key, value in self.experts.items()},
            "sources": self.sources,
            "explanation": self.explanation,
            "mechanism": self.mechanism,
        }
