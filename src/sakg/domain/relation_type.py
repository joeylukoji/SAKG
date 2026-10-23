"""Types de relations de l'ontologie (ARCHITECTURE.md §3.3)."""

from enum import StrEnum


class RelationType(StrEnum):
    """Type d'une relation orientée ``source → target``."""

    REALIZED_BY = "realized_by"
    CONSTRAINED_BY = "constrained_by"
    USED_BY = "used_by"
    IMPLEMENTED_BY = "implemented_by"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    EXPOSES = "exposes"
    MAPS_TO = "maps_to"
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    REFERENCES = "references"
    VERIFIES = "verifies"
    TESTS = "tests"
    DEPLOYED_IN = "deployed_in"
    DECIDED_BY = "decided_by"
    USES_TECHNOLOGY = "uses_technology"
    BELONGS_TO = "belongs_to"
