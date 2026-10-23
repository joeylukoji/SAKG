"""Comparaison de deux versions du graphe : qu'est-ce qui a changé dans l'architecture ?

Un changement est défini par le contenu au sens d'[ADR-005] : identité, type, nom, propriétés,
et le couple « nature de la preuve, confiance ». Déplacer une classe de dix lignes dans son
fichier ne change pas l'architecture et n'apparaît donc pas ici.

Trois catégories sont distinguées, pour les nœuds comme pour les relations : ajouté, supprimé,
modifié. Une relation dont seule la nature change (import de typage devenu import
d'exécution, relation supposée devenue observée) est *modifiée* : l'annoncer supprimée serait
affirmer un fait faux, et cacher le changement qui compte.
"""

from dataclasses import dataclass, field
from typing import Any

from sakg.domain import Edge, Node, NodeType
from sakg.graph import GraphSnapshot, KnowledgeGraph, edge_fingerprint, node_fingerprint


def describe_changes(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    """Ce qui a changé entre deux empreintes, propriété par propriété.

    Example:
        >>> describe_changes({"confidence": 0.6, "properties": {}}, {"confidence": 1.0, "properties": {}})
        ['confidence : 0.6 → 1.0']
        >>> describe_changes({"properties": {"type_only": True}}, {"properties": {}})
        ['properties.type_only : True → absent']
    """
    changes: list[str] = []
    for field_name in sorted(first.keys() | second.keys()):
        before, after = first.get(field_name), second.get(field_name)
        if before == after:
            continue
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(before.keys() | after.keys()):
                if before.get(key) != after.get(key):
                    changes.append(f"{field_name}.{key} : {_shown(before, key)} → {_shown(after, key)}")
        else:
            changes.append(f"{field_name} : {before} → {after}")
    return changes


def _shown(values: dict[str, Any], key: str) -> str:
    return repr(values[key]) if key in values else "absent"


@dataclass(frozen=True)
class ChangedNode:
    """Nœud présent dans les deux versions, mais dont le contenu a changé."""

    before: Node
    after: Node

    def changed_fields(self) -> list[str]:
        """Champs qui diffèrent, pour dire *ce qui* a changé et pas seulement *que* ça a changé."""
        return _changed_fields(node_fingerprint(self.before), node_fingerprint(self.after))

    def describe(self) -> list[str]:
        """Changements détaillés, par exemple ``properties.module : 'a' → 'b'``."""
        return describe_changes(node_fingerprint(self.before), node_fingerprint(self.after))


@dataclass(frozen=True)
class ChangedEdge:
    """Relation présente dans les deux versions, dont la nature a changé.

    Passer d'un import de typage à un import d'exécution ne supprime rien : la relation existe
    toujours, c'est ce qu'on en sait qui a changé.
    """

    before: Edge
    after: Edge

    def changed_fields(self) -> list[str]:
        """Champs qui diffèrent."""
        return _changed_fields(edge_fingerprint(self.before), edge_fingerprint(self.after))

    def describe(self) -> list[str]:
        """Changements détaillés, par exemple ``properties.type_only : True → absent``."""
        return describe_changes(edge_fingerprint(self.before), edge_fingerprint(self.after))


@dataclass(frozen=True)
class ArchitectureDiff:
    """Différences entre deux versions du graphe.

    Attributes:
        before: Version de départ.
        after: Version d'arrivée.
        added_nodes: Nœuds apparus.
        removed_nodes: Nœuds disparus.
        modified_nodes: Nœuds dont le contenu a changé.
        added_edges: Relations apparues.
        removed_edges: Relations disparues.
        modified_edges: Relations toujours présentes dont la nature a changé.
    """

    before: int = 0
    after: int = 0
    added_nodes: list[Node] = field(default_factory=list)
    removed_nodes: list[Node] = field(default_factory=list)
    modified_nodes: list[ChangedNode] = field(default_factory=list)
    added_edges: list[Edge] = field(default_factory=list)
    removed_edges: list[Edge] = field(default_factory=list)
    modified_edges: list[ChangedEdge] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Indique que l'architecture est identique d'une version à l'autre."""
        return not any(self.counts().values())

    def counts(self) -> dict[str, int]:
        """Volume de chaque catégorie de changement."""
        return {
            "nœuds ajoutés": len(self.added_nodes),
            "nœuds supprimés": len(self.removed_nodes),
            "nœuds modifiés": len(self.modified_nodes),
            "relations ajoutées": len(self.added_edges),
            "relations supprimées": len(self.removed_edges),
            "relations modifiées": len(self.modified_edges),
        }

    def by_type(self) -> dict[NodeType, int]:
        """Nombre de nœuds touchés par type, du plus concerné au moins concerné."""
        touched: dict[NodeType, int] = {}
        for node in [*self.added_nodes, *self.removed_nodes, *(change.after for change in self.modified_nodes)]:
            touched[node.type] = touched.get(node.type, 0) + 1
        return dict(sorted(touched.items(), key=lambda item: (-item[1], item[0].value)))

    def to_markdown(self) -> str:
        """Rapport lisible des changements d'architecture."""
        lines = [f"# Diff d'architecture : v{self.before} → v{self.after}", ""]
        if self.is_empty():
            return "\n".join([*lines, "Aucun changement d'architecture."]) + "\n"

        lines.append(" · ".join(f"{label} : {count}" for label, count in self.counts().items() if count))
        lines.append("")
        _append_section(lines, "Nœuds ajoutés", [f"`{node.id}`" for node in _by_id(self.added_nodes)])
        _append_section(lines, "Nœuds supprimés", [f"`{node.id}`" for node in _by_id(self.removed_nodes)])
        _append_section(
            lines,
            "Nœuds modifiés",
            [
                f"`{change.after.id}` — {' ; '.join(change.describe())}"
                for change in sorted(self.modified_nodes, key=lambda item: item.after.id)
            ],
        )
        _append_section(lines, "Relations ajoutées", [_edge_label(edge) for edge in _by_id(self.added_edges)])
        _append_section(lines, "Relations supprimées", [_edge_label(edge) for edge in _by_id(self.removed_edges)])
        _append_section(
            lines,
            "Relations modifiées",
            [
                f"{_edge_label(change.after)} — {' ; '.join(change.describe())}"
                for change in sorted(self.modified_edges, key=lambda item: item.after.id)
            ],
        )
        return "\n".join(lines).rstrip() + "\n"


class GraphDiffer:
    """Compare deux états du graphe.

    Example:
        >>> GraphDiffer().diff(before, after).to_markdown()  # doctest: +SKIP
    """

    def diff(self, before: GraphSnapshot, after: GraphSnapshot) -> ArchitectureDiff:
        """Différences entre deux snapshots."""
        return self.diff_graphs(before.graph, after.graph, before.version, after.version)

    def diff_graphs(
        self, before: KnowledgeGraph, after: KnowledgeGraph, before_version: int = 0, after_version: int = 0
    ) -> ArchitectureDiff:
        """Différences entre deux graphes, sans passer par des snapshots enregistrés."""
        old_nodes = {node.id: node for node in before.nodes()}
        new_nodes = {node.id: node for node in after.nodes()}
        old_edges = {edge.id: edge for edge in before.edges()}
        new_edges = {edge.id: edge for edge in after.edges()}

        return ArchitectureDiff(
            before=before_version,
            after=after_version,
            added_nodes=[new_nodes[node_id] for node_id in new_nodes.keys() - old_nodes.keys()],
            removed_nodes=[old_nodes[node_id] for node_id in old_nodes.keys() - new_nodes.keys()],
            modified_nodes=[
                ChangedNode(before=old_nodes[node_id], after=new_nodes[node_id])
                for node_id in old_nodes.keys() & new_nodes.keys()
                if node_fingerprint(old_nodes[node_id]) != node_fingerprint(new_nodes[node_id])
            ],
            added_edges=[new_edges[edge_id] for edge_id in new_edges.keys() - old_edges.keys()],
            removed_edges=[old_edges[edge_id] for edge_id in old_edges.keys() - new_edges.keys()],
            modified_edges=[
                ChangedEdge(before=old_edges[edge_id], after=new_edges[edge_id])
                for edge_id in old_edges.keys() & new_edges.keys()
                if edge_fingerprint(old_edges[edge_id]) != edge_fingerprint(new_edges[edge_id])
            ],
        )


def _changed_fields(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    return sorted(field_name for field_name in first if first[field_name] != second.get(field_name))


def _by_id(items: list[Any]) -> list[Any]:
    return sorted(items, key=lambda item: item.id)


def _append_section(lines: list[str], title: str, entries: list[str]) -> None:
    if not entries:
        return
    lines.append(f"## {title} ({len(entries)})")
    lines.extend(f"- {entry}" for entry in entries)
    lines.append("")


def _edge_label(edge: Edge) -> str:
    """Une relation telle qu'on la lit, nature comprise.

    Une dépendance de typage n'est pas une dépendance d'exécution, et une relation supposée
    n'est pas un fait : le rapport le dit.
    """
    notes = []
    if edge.properties.get("type_only"):
        notes.append("typage seul")
    if edge.provenance.confidence < 1.0:
        notes.append(f"confiance {edge.provenance.confidence:.1f}")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return f"`{edge.source_id}` —{edge.relation.value}→ `{edge.target_id}`{suffix}"
