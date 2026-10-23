"""Dérive entre le graphe enregistré et le code actuel (ARCHITECTURE.md §8).

``DriftDetector`` ne recharge ni ne modifie rien : on lui donne les deux graphes à comparer.
``ArchitectureService.detect_drift`` construit ``actual`` en recalculant la couche observée
sans l'enregistrer, pour ne jamais confondre une dérive réelle avec un nœud ajouté à la main
(``USER_DEFINED``) qui n'existe simplement pas dans le code.
"""

from dataclasses import dataclass

from sakg.analysis.diff import GraphDiffer
from sakg.domain import Edge
from sakg.graph import KnowledgeGraph

__all__ = ["DriftDetector", "DriftReport"]


@dataclass(frozen=True)
class DriftReport:
    """Distance de Jaccard entre les relations enregistrées et celles du code actuel.

    ``Drift(G_a, G_c) = 1 − |E_a ∩ E_c| / |E_a ∪ E_c|`` (ARCHITECTURE.md §8), où l'identité
    d'une relation est son ``(source, relation, cible)`` — un changement de propriété seul
    (typage devenu exécution) ne compte donc pas comme une dérive.

    Attributes:
        drift_score: 0 si le graphe enregistré décrit encore le code, 1 s'ils n'ont plus aucune
            relation en commun.
        missing_in_code: Relations que le graphe enregistré affirme, absentes du code actuel.
        undocumented_in_code: Relations présentes dans le code actuel, absentes du graphe
            enregistré.
    """

    drift_score: float
    missing_in_code: tuple[Edge, ...]
    undocumented_in_code: tuple[Edge, ...]

    def has_drifted(self) -> bool:
        """Vrai si le graphe enregistré ne décrit plus exactement le code."""
        return self.drift_score > 0

    def to_markdown(self) -> str:
        """Rapport lisible : le score, puis ce qui a changé."""
        lines = [f"# Dérive architecture ↔ code : {self.drift_score:.0%}", ""]
        if not self.has_drifted():
            return "\n".join([*lines, "Le graphe enregistré décrit encore le code."]) + "\n"
        lines.append(
            f"{len(self.undocumented_in_code)} relation(s) apparue(s) dans le code, "
            f"{len(self.missing_in_code)} disparue(s) du graphe enregistré."
        )
        lines.append("")
        _append_edges(lines, "Apparues dans le code", self.undocumented_in_code)
        _append_edges(lines, "Disparues du graphe enregistré", self.missing_in_code)
        return "\n".join(lines).rstrip() + "\n"


class DriftDetector:
    """Compare le graphe voulu/enregistré (``G_a``) au graphe extrait du code (``G_c``)."""

    def __init__(self, differ: GraphDiffer | None = None) -> None:
        self._differ = differ if differ is not None else GraphDiffer()

    def detect(self, intended: KnowledgeGraph, actual: KnowledgeGraph) -> DriftReport:
        """Score de dérive et détail des relations qui diffèrent entre les deux graphes."""
        diff = self._differ.diff_graphs(intended, actual)
        intended_edges = {edge.id for edge in intended.edges()}
        actual_edges = {edge.id for edge in actual.edges()}
        union = intended_edges | actual_edges
        score = 0.0 if not union else 1 - len(intended_edges & actual_edges) / len(union)
        return DriftReport(
            drift_score=score,
            missing_in_code=tuple(diff.removed_edges),
            undocumented_in_code=tuple(diff.added_edges),
        )


def _append_edges(lines: list[str], title: str, edges: tuple[Edge, ...]) -> None:
    if not edges:
        return
    lines.append(f"## {title} ({len(edges)})")
    lines.extend(f"- {edge.source_id} --{edge.relation.value}--> {edge.target_id}" for edge in sorted(edges, key=lambda e: e.id))
    lines.append("")
