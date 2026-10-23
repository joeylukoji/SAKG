"""Erreurs du domaine et du graphe."""


class SakgError(Exception):
    """Erreur de base de SAKG."""


class DuplicateNodeError(SakgError):
    """Un nœud portant cet identifiant existe déjà."""


class DuplicateEdgeError(SakgError):
    """Une relation portant cet identifiant existe déjà."""


class NodeNotFoundError(SakgError):
    """Aucun nœud ne porte cet identifiant."""


class EdgeNotFoundError(SakgError):
    """Aucune relation ne porte cet identifiant."""


class OntologyViolationError(SakgError):
    """La relation n'est pas autorisée par l'ontologie."""


class SnapshotNotFoundError(SakgError):
    """Aucun snapshot archivé ne porte cette version."""
