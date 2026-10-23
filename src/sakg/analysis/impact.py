"""Analyse d'impact : quels éléments d'architecture un changement touche-t-il ?"""

import re
from dataclasses import dataclass, field

from sakg.domain import Edge, Node, NodeType, RelationType
from sakg.graph import DEPENDENCY_RELATIONS, BoundedBfsStrategy, Direction, GraphQueryEngine, TraversalStrategy

MIN_TOKEN_LENGTH = 3

DEFAULT_IMPACT_DEPTH = 2
"""Nombre de sauts de dépendance propagés depuis les nœuds touchés."""

STRUCTURAL_DEPTH = 2
"""Méthode → classe → fichier : la remontée structurelle ne dépasse pas deux niveaux."""

DEFAULT_SEED_LIMIT = 5
"""Nombre maximal de points de départ retenus parmi les correspondances de même qualité."""

_NO_TRAVERSAL = BoundedBfsStrategy(max_depth=0)
"""Stratégie neutre : les nœuds de départ, et rien d'autre."""

STOP_WORDS = frozenset(
    {
        "ajouter",
        "ajout",
        "add",
        "adding",
        "supprimer",
        "retirer",
        "remove",
        "delete",
        "modifier",
        "changer",
        "change",
        "update",
        "mettre",
        "jour",
        "refactor",
        "corriger",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "les",
        "des",
        "une",
        "aux",
        "avec",
        "dans",
        "pour",
        "sur",
        "par",
        "que",
        "qui",
        "son",
        "ses",
        "est",
        "sont",
        "new",
        "nouveau",
        "nouvelle",
        "système",
        "systeme",
        "system",
        "support",
    }
)
"""Mots trop courants pour désigner un élément d'architecture."""


WORD_WEIGHT = 1.0
"""Poids d'un mot écrit tel quel dans la description."""

FRAGMENT_WEIGHT = 0.3
"""Poids d'un fragment issu du découpage d'un identifiant : ``type`` dans ``TypeScript``."""

MIN_MATCH_COVERAGE = 0.5
"""En deçà, la correspondance est jugée faible et signalée dans le rapport."""


def tokenize(text: str) -> list[str]:
    """Mots significatifs d'une description, en minuscules et sans doublons.

    Les identifiants ``CamelCase`` et ``snake_case`` sont éclatés en mots.

    Example:
        >>> tokenize("Ajouter les paiements mobiles à PaymentService")
        ['paiements', 'mobiles', 'paymentservice', 'payment', 'service']
    """
    return list(weighted_tokens(text))


def weighted_tokens(text: str) -> dict[str, float]:
    """Jetons avec leur poids : un mot entier compte plus qu'un fragment d'identifiant.

    Sans cette distinction, « TypeScript » vaudrait autant que ``type`` et ``script``, et
    ferait correspondre tout nœud contenant l'un de ces fragments.

    Example:
        >>> weighted_tokens("PaymentService")
        {'paymentservice': 1.0, 'payment': 0.3, 'service': 0.3}
    """
    weights: dict[str, float] = {}
    for raw in re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*", text):
        fragments = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", raw)
        for candidate, weight in [(raw, WORD_WEIGHT), *((fragment, FRAGMENT_WEIGHT) for fragment in fragments)]:
            token = candidate.lower().strip("_")
            if len(token) < MIN_TOKEN_LENGTH or token in STOP_WORDS:
                continue
            weights[token] = max(weights.get(token, 0.0), weight)
    return weights


@dataclass(frozen=True)
class ChangeRequest:
    """Changement envisagé, décrit en langage naturel ou par des nœuds précis.

    Attributes:
        description: Description libre, par exemple « Ajouter les paiements mobiles ».
        target_node_ids: Nœuds imposés ; s'ils sont fournis, la recherche lexicale est ignorée.
        kind: Nature du changement, libre (``change``, ``add``, ``remove``…).
    """

    description: str
    target_node_ids: tuple[str, ...] = ()
    kind: str = "change"


@dataclass(frozen=True)
class ImpactReport:
    """Éléments touchés par un changement, groupés par type de nœud.

    Attributes:
        change: Demande analysée.
        seeds: Nœuds de départ retenus.
        affected: Nœuds touchés, groupés par type.
        scores: Identifiant → score, décroissant avec la distance au point de départ.
        reasons: Identifiant → relation par laquelle le nœud a été atteint.
        warnings: Difficultés rencontrées, par exemple une correspondance faible.
    """

    change: ChangeRequest
    seeds: tuple[str, ...] = ()
    affected: dict[NodeType, list[Node]] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def by_type(self, node_type: NodeType) -> list[Node]:
        """Nœuds touchés d'un type donné."""
        return self.affected.get(node_type, [])

    def all_nodes(self) -> list[Node]:
        """Tous les nœuds touchés, du plus au moins concerné."""
        nodes = [node for group in self.affected.values() for node in group]
        return sorted(nodes, key=lambda node: (-self.scores.get(node.id, 0.0), node.id))

    def is_empty(self) -> bool:
        """Indique qu'aucun nœud n'a été touché."""
        return not self.affected

    def to_markdown(self) -> str:
        """Rapport lisible, groupé par niveau d'architecture."""
        lines = [f"# Impact : {self.change.description}", ""]
        if self.is_empty():
            lines.append("Aucun élément d'architecture identifié.")
        for warning in self.warnings:
            lines.append(f"> {warning}")
        if self.warnings:
            lines.append("")
        # Du niveau le plus abstrait (exigences, composants) au plus concret (fichiers).
        for node_type in sorted(self.affected, key=lambda item: (-_type_priority(item), item.value)):
            nodes = self.affected[node_type]
            lines.append(f"## {node_type.value} ({len(nodes)})")
            for node in sorted(nodes, key=lambda node: (-self.scores.get(node.id, 0.0), node.id)):
                if node.id in self.seeds:
                    detail = "point de départ"
                else:
                    detail = self.reasons.get(node.id, "atteint par propagation")
                lines.append(f"- `{node.id}` — score {self.scores.get(node.id, 0.0):.2f} — {detail}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


class ImpactAnalyzer:
    """Localise les nœuds concernés par un changement, puis propage aux dépendants.

    L'analyse se fait en deux temps :

    1. **remontée structurelle** — du symbole vers sa classe puis son fichier, en suivant
       ``contains`` à rebours. Ces sauts ne coûtent rien : ils ne changent pas de sujet, ils
       changent de niveau de description.
    2. **propagation des dépendances** — depuis cet ensemble, vers ce qui en dépend. Le score
       décroît à chaque saut, de sorte qu'un appelant direct pèse plus qu'un dépendant lointain.
    """

    def __init__(self, query: GraphQueryEngine, strategy: TraversalStrategy | None = None) -> None:
        self._query = query
        self._structural = BoundedBfsStrategy(
            max_depth=STRUCTURAL_DEPTH,
            relations=frozenset({RelationType.CONTAINS}),
            direction=Direction.IN,
        )
        self._strategy = (
            strategy
            if strategy is not None
            else BoundedBfsStrategy(
                max_depth=DEFAULT_IMPACT_DEPTH, relations=frozenset(DEPENDENCY_RELATIONS), direction=Direction.IN
            )
        )

    def locate(self, change: ChangeRequest, seed_limit: int = DEFAULT_SEED_LIMIT) -> list[Node]:
        """Nœuds de départ effectivement retenus par :meth:`analyze`.

        Ce sont les nœuds de meilleure couverture, dans la limite de ``seed_limit`` ; pour la
        liste complète des candidats, voir :meth:`candidates`.
        """
        return [node for node, _ in self._seeds(change, seed_limit)[0]]

    def candidates(self, change: ChangeRequest) -> list[tuple[Node, float]]:
        """Tous les nœuds reconnus dans la description, avec leur couverture entre 0 et 1."""
        if change.target_node_ids:
            found = (self._query.get_node(node_id) for node_id in change.target_node_ids)
            return [(node, 1.0) for node in found if node is not None]

        wanted = weighted_tokens(change.description)
        total = sum(wanted.values())
        if not total:
            return []
        scored: list[tuple[Node, float]] = []
        for node in self._query.nodes():
            haystack = set(weighted_tokens(node.name)) | set(
                weighted_tokens(str(node.properties.get("qualified_name", "")))
            )
            matched = sum(weight for token, weight in wanted.items() if token in haystack)
            if matched:
                scored.append((node, matched / total))
        scored.sort(key=lambda item: (-item[1], -_type_priority(item[0].type), _is_private(item[0]), item[0].id))
        return scored

    def _seeds(self, change: ChangeRequest, seed_limit: int) -> tuple[list[tuple[Node, float]], list[str], bool]:
        """Nœuds de départ retenus, avertissements, et si la correspondance est jugée faible."""
        warnings: list[str] = []
        if change.target_node_ids:
            known = {node.id for node in self._query.nodes()}
            missing = [node_id for node_id in change.target_node_ids if node_id not in known]
            warnings.extend(f"nœud demandé introuvable : {node_id}" for node_id in missing)
            # Une cible explicite n'est jamais tronquée : l'utilisateur a déjà tranché.
            return self.candidates(change), warnings, False

        candidates = self.candidates(change)
        if not candidates:
            return [], ["aucun nœud ne correspond à la description ; préciser un identifiant avec --node"], False

        best = candidates[0][1]
        tied = [item for item in candidates if item[1] == best]
        weak = best < MIN_MATCH_COVERAGE
        if weak:
            warnings.append(
                f"correspondance faible ({best:.0%} de la description reconnue) : "
                "les nœuds trouvés sont listés sans propagation ; préciser un identifiant avec --node"
            )
        if len(tied) > seed_limit:
            warnings.append(f"{len(tied)} nœuds à égalité, {seed_limit} retenus comme points de départ")
        return tied[:seed_limit], warnings, weak

    def analyze(self, change: ChangeRequest, seed_limit: int = DEFAULT_SEED_LIMIT) -> ImpactReport:
        """Construit le rapport d'impact du changement.

        Seuls les nœuds de meilleure couverture servent de point de départ : une
        correspondance partielle (``PaymentController`` pour « changer PaymentService »)
        reste atteignable par propagation, mais ne fausse pas les scores.
        """
        seeds, warnings, weak = self._seeds(change, seed_limit)
        if not seeds:
            return ImpactReport(change=change, warnings=tuple(warnings))

        seed_ids = tuple(node.id for node, _ in seeds)
        # Une correspondance faible ne se propage pas : mieux vaut une courte liste de pistes
        # qu'un rapport large fondé sur un fragment de mot.
        structural = self._query.traverse(seed_ids, self._structural if not weak else _NO_TRAVERSAL)
        dependency = self._query.traverse(list(structural.visited), self._strategy if not weak else _NO_TRAVERSAL)

        scores = dict.fromkeys(structural.visited, 1.0)
        for node_id, depth in dependency.visited.items():
            scores[node_id] = max(scores.get(node_id, 0.0), dependency.scores[node_id] if depth else 1.0)

        reasons = self._reasons(structural.edges + dependency.edges, seed_ids)
        affected: dict[NodeType, list[Node]] = {}
        for node_id in scores:
            node = self._query.get_node(node_id)
            if node is not None:
                affected.setdefault(node.type, []).append(node)
        return ImpactReport(
            change=change,
            seeds=seed_ids,
            affected=affected,
            scores=scores,
            reasons=reasons,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _reasons(edges: list[Edge], seed_ids: tuple[str, ...]) -> dict[str, str]:
        """Pourquoi chaque nœud figure au rapport : la première relation par laquelle on l'atteint."""
        reasons: dict[str, str] = {}
        for edge in edges:
            reached = edge.source_id  # la propagation remonte les relations
            if reached not in seed_ids and reached not in reasons:
                reasons[reached] = f"{edge.relation.value} vers `{edge.target_id}`"
        return reasons


_TYPE_PRIORITY = {
    NodeType.REQUIREMENT: 5,
    NodeType.USE_CASE: 5,
    NodeType.COMPONENT: 4,
    NodeType.SERVICE: 4,
    NodeType.MODULE: 3,
    NodeType.ENDPOINT: 3,
    NodeType.TABLE: 3,
    NodeType.CLASS: 2,
    NodeType.INTERFACE: 2,
    NodeType.METHOD: 1,
    NodeType.FUNCTION: 1,
    NodeType.FILE: 0,
}


def _type_priority(node_type: NodeType) -> int:
    return _TYPE_PRIORITY.get(node_type, 2)


def _is_private(node: Node) -> bool:
    """Un symbole privé ou spécial est un point de départ moins probable qu'un symbole public."""
    return node.name.startswith("_")
