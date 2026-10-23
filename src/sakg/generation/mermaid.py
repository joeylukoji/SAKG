"""Génération de diagrammes Mermaid depuis le graphe."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sakg.domain import Node, NodeType, RelationType
from sakg.generation.projection import DiagramView, ViewProjection
from sakg.graph import KnowledgeGraph

MERMAID_ARROWS = {
    RelationType.INHERITS: "--|>",
    RelationType.IMPLEMENTS: "..|>",
    RelationType.DEPENDS_ON: "..>",
    RelationType.CALLS: "..>",
}


@dataclass(frozen=True)
class Diagram:
    """Diagramme généré.

    Attributes:
        view: Vue représentée.
        format: Format de sortie, par exemple ``mermaid``.
        source: Code source du diagramme.
        graph_version: Version du graphe dont il est issu.
    """

    view: DiagramView
    format: str
    source: str
    graph_version: int

    def to_markdown(self) -> str:
        """Diagramme encadré par un bloc de code, prêt à être écrit dans un fichier ``.md``."""
        return f"```{self.format}\n{self.source}\n```\n"


class DiagramGenerator(Protocol):
    """Rendu d'un graphe projeté dans un langage de diagramme."""

    @property
    def format(self) -> str:
        """Format produit."""
        ...

    def generate(self, graph: KnowledgeGraph, view: DiagramView, focus: Sequence[str] | None = None) -> Diagram:
        """Produit le diagramme d'une vue."""
        ...


class MermaidGenerator:
    """Rendu Mermaid ; seule la vue CLASS est implémentée au MVP.

    Example:
        >>> MermaidGenerator().generate(graph, DiagramView.CLASS)  # doctest: +SKIP
    """

    @property
    def format(self) -> str:
        """Format produit."""
        return "mermaid"

    def generate(self, graph: KnowledgeGraph, view: DiagramView, focus: Sequence[str] | None = None) -> Diagram:
        """Projette le graphe puis produit le code Mermaid.

        Raises:
            UnsupportedViewError: Si la vue n'a pas de projection.
        """
        projected = ViewProjection.for_view(view).project(graph, focus)
        source = self._class_diagram(projected) if view is DiagramView.CLASS else self._flowchart(projected)
        return Diagram(view=view, format=self.format, source=source, graph_version=graph.version)

    def _class_diagram(self, graph: KnowledgeGraph) -> str:
        labels = _unique_labels([node for node in graph.nodes() if node.type is not NodeType.METHOD])
        lines = ["classDiagram"]
        for node_id, label in labels.items():
            methods = [
                graph.get_node(edge.target_id)
                for edge in graph.out_edges(node_id)
                if edge.relation is RelationType.CONTAINS
            ]
            # Les méthodes privées et spéciales n'appartiennent pas à l'interface d'une classe.
            members = sorted(
                method.name for method in methods if method is not None and not method.name.startswith("_")
            )
            node = graph.get_node(node_id)
            stereotype = ["        <<interface>>"] if node is not None and node.type is NodeType.INTERFACE else []
            if members or stereotype:
                lines.append(f"    class {label} {{")
                lines.extend(stereotype)
                lines.extend(f"        +{member}()" for member in members)
                lines.append("    }")
            else:
                lines.append(f"    class {label}")

        lines.extend(self._relations(graph, labels))
        return "\n".join(lines)

    def _relations(self, graph: KnowledgeGraph, labels: dict[str, str]) -> list[str]:
        """Flèches entre classes, appels de méthodes remontés à leurs classes propriétaires."""
        owners = {
            edge.target_id: edge.source_id
            for edge in graph.edges()
            if edge.relation is RelationType.CONTAINS and edge.source_id in labels
        }
        drawn: set[tuple[str, str, str]] = set()
        lines: list[str] = []
        for edge in graph.edges():
            source = edge.source_id if edge.source_id in labels else owners.get(edge.source_id)
            target = edge.target_id if edge.target_id in labels else owners.get(edge.target_id)
            arrow = MERMAID_ARROWS.get(edge.relation)
            if arrow is None or source is None or target is None or source == target:
                continue
            key = (source, arrow, target)
            if key in drawn:
                continue
            drawn.add(key)
            lines.append(f"    {labels[source]} {arrow} {labels[target]}")
        return lines

    def _flowchart(self, graph: KnowledgeGraph) -> str:
        labels = _unique_labels(graph.nodes())
        lines = ["flowchart LR"]
        lines.extend(f'    {label}["{graph.get_node(node_id).name}"]' for node_id, label in labels.items())  # type: ignore[union-attr]
        for edge in graph.edges():
            if edge.source_id in labels and edge.target_id in labels:
                lines.append(f"    {labels[edge.source_id]} -->|{edge.relation.value}| {labels[edge.target_id]}")
        return "\n".join(lines)


def _unique_labels(nodes: Sequence[Node]) -> dict[str, str]:
    """Identifiant de nœud → étiquette Mermaid unique et lisible.

    Deux classes homonymes dans des modules différents sont distinguées par un suffixe, sans
    quoi Mermaid les fusionnerait en une seule boîte.
    """
    counts: dict[str, int] = {}
    for node in nodes:
        counts[_sanitize(node.name)] = counts.get(_sanitize(node.name), 0) + 1

    labels: dict[str, str] = {}
    used: set[str] = set()
    for node in nodes:
        label = _sanitize(node.name)
        if counts[label] > 1:
            module = _sanitize(str(node.properties.get("module", "")).replace(".", "_"))
            label = f"{label}_{module}" if module else label
        candidate, suffix = label, 2
        while candidate in used:
            candidate, suffix = f"{label}_{suffix}", suffix + 1
        used.add(candidate)
        labels[node.id] = candidate
    return labels


def _sanitize(text: str) -> str:
    cleaned = re.sub(r"\W", "_", text).strip("_")
    return cleaned or "node"
