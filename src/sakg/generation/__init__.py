"""Génération : diagrammes et documentation."""

from sakg.generation.mermaid import Diagram, DiagramGenerator, MermaidGenerator
from sakg.generation.projection import DiagramView, UnsupportedViewError, ViewProjection

__all__ = [
    "Diagram",
    "DiagramGenerator",
    "DiagramView",
    "MermaidGenerator",
    "UnsupportedViewError",
    "ViewProjection",
]
