"""Nœud typé du graphe."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sakg.domain.node_type import NodeType
from sakg.domain.provenance import Provenance

QUALIFIED_NAME_SEPARATOR = "::"


def make_node_id(node_type: NodeType, path: str, qualified_name: str) -> str:
    """Construit un identifiant stable ``<type>:<chemin>::<nom qualifié>``.

    Args:
        node_type: Type du nœud, utilisé comme préfixe.
        path: Chemin relatif du fichier en séparateurs ``/`` ; vide pour un nœud qui ne vient
            pas d'un fichier précis, comme une exigence ou une technologie.
        qualified_name: Nom qualifié du symbole, par exemple ``PaymentService.pay``.

    Example:
        >>> make_node_id(NodeType.CLASS, "src/payment/service.py", "PaymentService")
        'class:src/payment/service.py::PaymentService'
        >>> make_node_id(NodeType.REQUIREMENT, "", "REQ-001")
        'requirement:REQ-001'
    """
    posix_path = path.replace("\\", "/")
    if not posix_path:
        return f"{node_type.value}:{qualified_name}"
    return f"{node_type.value}:{posix_path}{QUALIFIED_NAME_SEPARATOR}{qualified_name}"


class Node(BaseModel):
    """Élément typé du graphe, toujours accompagné de sa provenance.

    Les valeurs de ``properties`` doivent être sérialisables en JSON : elles entrent dans le
    hash du graphe et dans les fichiers de ``.architect/``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    type: NodeType
    name: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def _check_id_prefix(self) -> Self:
        if not self.id.startswith(f"{self.type.value}:"):
            raise ValueError(f"l'identifiant {self.id!r} doit commencer par '{self.type.value}:'")
        return self

    def qualified_name(self) -> str:
        """Retourne la partie « nom qualifié » de l'identifiant, ou le nom à défaut."""
        _, separator, qualified = self.id.partition(QUALIFIED_NAME_SEPARATOR)
        return qualified if separator and qualified else self.name
