"""Relation orientée et typée entre deux nœuds."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sakg.domain.provenance import Provenance
from sakg.domain.relation_type import RelationType


def make_edge_id(source_id: str, relation: RelationType, target_id: str) -> str:
    """Construit l'identifiant stable ``<source>-[<relation>]-><cible>``."""
    return f"{source_id}-[{relation.value}]->{target_id}"


class Edge(BaseModel):
    """Relation ``source → target`` ; l'identifiant est déduit s'il n'est pas fourni.

    Comme pour :class:`~sakg.domain.node.Node`, ``properties`` doit être sérialisable en JSON.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default="", description="Déduit de make_edge_id si vide.")
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation: RelationType
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _default_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("id"):
            try:
                relation = RelationType(data["relation"])
                data = {**data, "id": make_edge_id(data["source_id"], relation, data["target_id"])}
            except (KeyError, ValueError):
                pass  # Les champs manquants ou invalides sont signalés par la validation standard.
        return data
