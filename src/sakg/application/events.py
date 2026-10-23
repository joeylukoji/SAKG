"""Événements de domaine et bus de publication (Observer)."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Fait métier déjà survenu."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, kw_only=True)
class GraphChanged(DomainEvent):
    """Le graphe a changé et une nouvelle version a été enregistrée."""

    version: int
    command: str


@dataclass(frozen=True, kw_only=True)
class ProposalCreated(DomainEvent):
    """Une proposition d'architecture attend une décision humaine."""

    proposal_id: str


@dataclass(frozen=True, kw_only=True)
class ValidationCompleted(DomainEvent):
    """Une validation des règles d'architecture s'est terminée."""

    passed: bool


Handler = Callable[[DomainEvent], None]


class EventBus:
    """Publication synchrone : les abonnés d'un type reçoivent aussi ses sous-types.

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe(GraphChanged, lambda event: print(event))
        >>> bus.publish(GraphChanged(version=1, command="AddNodeCommand"))  # doctest: +SKIP
    """

    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[Handler]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        """Abonne un gestionnaire à un type d'événement."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Transmet l'événement à tous les gestionnaires concernés.

        Un gestionnaire qui échoue est journalisé et n'empêche ni les autres gestionnaires
        ni la commande à l'origine de l'événement : les abonnés (régénération de diagrammes,
        invalidation de cache) sont accessoires à la mutation, déjà validée et enregistrée.
        """
        for event_type, handlers in self._subscribers.items():
            if not isinstance(event, event_type):
                continue
            for handler in handlers:
                try:
                    handler(event)
                except Exception:
                    _logger.exception("gestionnaire en échec pour %s", type(event).__name__)
