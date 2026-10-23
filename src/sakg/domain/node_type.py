"""Types de nœuds de l'ontologie (ARCHITECTURE.md §3.2)."""

from enum import StrEnum


class NodeType(StrEnum):
    """Type d'un nœud du graphe ; la valeur sert de préfixe aux identifiants."""

    # Fonctionnel
    PROJECT = "project"
    REQUIREMENT = "requirement"
    ACTOR = "actor"
    USE_CASE = "use_case"
    BUSINESS_RULE = "business_rule"
    CONSTRAINT = "constraint"
    # Architecture
    SYSTEM = "system"
    SUBSYSTEM = "subsystem"
    MODULE = "module"
    COMPONENT = "component"
    SERVICE = "service"
    LAYER = "layer"
    PACKAGE = "package"
    # Code
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    FILE = "file"
    DIRECTORY = "directory"
    # API
    ENDPOINT = "endpoint"
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    MESSAGE = "message"
    # Données
    DATABASE = "database"
    SCHEMA = "schema"
    TABLE = "table"
    COLUMN = "column"
    INDEX = "index"
    # Infrastructure
    CONTAINER = "container"
    IMAGE = "image"
    NETWORK = "network"
    VOLUME = "volume"
    CLOUD_SERVICE = "cloud_service"
    DEPLOYMENT = "deployment"
    # Qualité
    TEST = "test"
    TEST_SUITE = "test_suite"
    FINDING = "finding"
    ARCHITECTURE_VIOLATION = "architecture_violation"
    # Décision
    TECHNOLOGY = "technology"
    ADR = "adr"
    ALTERNATIVE = "alternative"
    TRADE_OFF = "trade_off"
