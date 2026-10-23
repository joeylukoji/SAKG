"""Chargement des règles déclarées dans ``.architect/rules/*.yaml``.

Le ``type`` d'une entrée YAML désigne une classe enregistrée dans :func:`default_rule_registry` ;
ajouter une règle est une nouvelle classe et une ligne d'enregistrement, sans toucher au
chargeur (règle 6 d'AGENTS.md).
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from sakg.domain import SakgError
from sakg.validation.rules import ArchitectureRule, LayerDependencyRule, NoCycleRule

RuleFactory = Callable[[Mapping[str, Any]], ArchitectureRule]

__all__ = ["RuleLoader", "RuleRegistry", "UnknownRuleTypeError", "default_rule_registry"]


class UnknownRuleTypeError(SakgError):
    """Le ``type`` d'une entrée de ``.architect/rules/*.yaml`` n'est enregistré dans aucun registre."""


class RuleRegistry:
    """Types de règles disponibles, par nom déclaré dans le YAML."""

    def __init__(self) -> None:
        self._factories: dict[str, RuleFactory] = {}

    def register(self, type_name: str, factory: RuleFactory) -> None:
        """Enregistre un type de règle (règle 6 d'AGENTS.md)."""
        self._factories[type_name] = factory

    def build(self, type_name: str, config: Mapping[str, Any]) -> ArchitectureRule:
        """Construit une règle depuis sa configuration.

        Raises:
            UnknownRuleTypeError: Si ``type_name`` n'est enregistré nulle part.
        """
        factory = self._factories.get(type_name)
        if factory is None:
            raise UnknownRuleTypeError(f"type de règle inconnu : {type_name!r}")
        return factory(config)


def default_rule_registry() -> RuleRegistry:
    """Registre avec les types de règles fournis par SAKG."""
    registry = RuleRegistry()
    registry.register("layer_dependency", LayerDependencyRule.from_config)
    registry.register("no_cycle", NoCycleRule.from_config)
    return registry


class RuleLoader:
    """Lit ``.architect/rules/*.yaml`` et construit les règles qui y sont déclarées."""

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        self._registry = registry if registry is not None else default_rule_registry()

    def load(self, rules_dir: Path) -> list[ArchitectureRule]:
        """Règles déclarées dans le dossier, dans l'ordre des fichiers puis des entrées.

        Un dossier absent (projet jamais initialisé, ou sans règle) ne produit aucune règle
        plutôt qu'une erreur.

        Raises:
            UnknownRuleTypeError: Si une entrée déclare un ``type`` inconnu.
        """
        if not rules_dir.is_dir():
            return []
        rules: list[ArchitectureRule] = []
        for path in sorted(rules_dir.glob("*.yaml")):
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            entries = loaded if isinstance(loaded, list) else [loaded]
            for entry in entries:
                rules.append(self._registry.build(str(entry["type"]), entry))
        return rules
