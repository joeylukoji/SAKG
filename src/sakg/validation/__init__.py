"""Validation : règles d'architecture (ARCHITECTURE.md §4.4)."""

from sakg.validation.findings import Finding, Severity, ValidationReport
from sakg.validation.loader import RuleLoader, RuleRegistry, UnknownRuleTypeError, default_rule_registry
from sakg.validation.rules import ArchitectureRule, LayerDependencyRule, NoCycleRule
from sakg.validation.validator import ArchitectureValidator

__all__ = [
    "ArchitectureRule",
    "ArchitectureValidator",
    "Finding",
    "LayerDependencyRule",
    "NoCycleRule",
    "RuleLoader",
    "RuleRegistry",
    "Severity",
    "UnknownRuleTypeError",
    "ValidationReport",
    "default_rule_registry",
]
