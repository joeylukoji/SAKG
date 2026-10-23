"""Provenance : la preuve attachée à chaque nœud et relation (ARCHITECTURE.md §3.4)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceType(StrEnum):
    """Nature de la preuve d'une information du graphe."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    GENERATED = "GENERATED"
    USER_DEFINED = "USER_DEFINED"
    RECOMMENDED = "RECOMMENDED"


FACT_EVIDENCE_TYPES = frozenset({EvidenceType.OBSERVED, EvidenceType.USER_DEFINED})


class Evidence(BaseModel):
    """Emplacement dans le code source qui justifie une information."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    snippet: str | None = None

    @model_validator(mode="after")
    def _check_line_range(self) -> Self:
        if self.end_line is not None and (self.line is None or self.end_line < self.line):
            raise ValueError("end_line exige line et doit être supérieur ou égal à line")
        return self


class Provenance(BaseModel):
    """Origine, méthode de détection et niveau de confiance d'une information.

    Attributes:
        evidence_type: Nature de la preuve.
        confidence: Confiance entre 0.0 et 1.0.
        detected_by: Méthode de détection, par exemple ``AST_IMPORT_ANALYSIS``.
        evidence: Emplacement dans le code, s'il existe.
        graph_version: Version du graphe au moment de la création.
        commit_sha: Commit analysé, s'il est connu.
        created_at: Horodatage UTC de création.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_type: EvidenceType
    confidence: float = Field(ge=0.0, le=1.0)
    detected_by: str = Field(min_length=1)
    evidence: Evidence | None = None
    graph_version: int = Field(default=0, ge=0)
    commit_sha: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_fact(self) -> bool:
        """Indique si l'information est un fait (observé ou saisi) plutôt qu'une hypothèse."""
        return self.evidence_type in FACT_EVIDENCE_TYPES
