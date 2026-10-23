"""Bus de commandes : journal, annulation et création de snapshots."""

from sakg.application.commands import GraphCommand
from sakg.application.events import EventBus, GraphChanged
from sakg.domain import SakgError
from sakg.graph import GraphRepository, GraphSnapshot, KnowledgeGraph


class NothingToUndoError(SakgError):
    """Aucune commande n'est présente dans le journal."""


class CommandBus:
    """Exécute les commandes, incrémente la version et enregistre un snapshot.

    Attributes:
        graph: Graphe muté par les commandes.

    Example:
        >>> bus = CommandBus(graph, repository, events)  # doctest: +SKIP
        >>> snapshot = bus.execute(AddNodeCommand(node))  # doctest: +SKIP
    """

    def __init__(
        self,
        graph: KnowledgeGraph,
        repository: GraphRepository,
        events: EventBus | None = None,
        *,
        commit_sha: str | None = None,
    ) -> None:
        self.graph = graph
        self._repository = repository
        self._events = events
        self.commit_sha = commit_sha
        """Commit du code analysé, repris dans les snapshots ; à rafraîchir avant un reverse."""
        self._history: list[GraphCommand] = []

    @property
    def history(self) -> list[GraphCommand]:
        """Commandes exécutées et non annulées, dans l'ordre."""
        return list(self._history)

    def execute(self, command: GraphCommand) -> GraphSnapshot:
        """Exécute la commande puis enregistre une nouvelle version.

        Si la commande échoue, le graphe n'est ni versionné, ni sauvegardé, ni journalisé.
        Si c'est l'enregistrement qui échoue, la mutation reste appliquée en mémoire et
        annulable par :meth:`undo_last`.
        """
        command.execute(self.graph)
        self._history.append(command)
        return self._commit(command.label)

    def undo_last(self) -> GraphSnapshot:
        """Annule la dernière commande et enregistre une nouvelle version.

        Raises:
            NothingToUndoError: Si le journal est vide.
        """
        if not self._history:
            raise NothingToUndoError("aucune commande à annuler")
        command = self._history[-1]
        command.undo(self.graph)  # le journal n'est dépilé qu'après une annulation réussie
        self._history.pop()
        return self._commit(f"undo:{command.label}")

    def _commit(self, label: str) -> GraphSnapshot:
        self.graph.version += 1
        snapshot = self._repository.save(self.graph, label=label, commit_sha=self.commit_sha)
        if self._events is not None:
            self._events.publish(GraphChanged(version=snapshot.version, command=label))
        return snapshot
