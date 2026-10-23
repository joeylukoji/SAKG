# AGENTS.md — consignes pour Claude Code, Cursor et Codex

## Contexte
SAKG (Software Architecture Knowledge Graph) construit un graphe sémantique et versionné de
l'architecture d'un logiciel. Lire avant toute tâche :
- `docs/ARCHITECTURE.md` — couches, modules, patterns, flux
- `docs/uml/class-diagram.md` — classes cibles (Mermaid)
- `docs/uml/use-case-diagram.md` — cas d'utilisation UC01–UC17

## Règles d'architecture (non négociables)
1. `src/sakg/domain` et `src/sakg/graph` n'importent AUCUNE bibliothèque externe hors
   Pydantic, NetworkX et la bibliothèque standard.
2. Les interfaces (`cli`, `mcp`, `api`) n'appellent que `ArchitectureService`.
3. Toute création de `Node` ou `Edge` fournit une `Provenance` complète.
4. Toute modification du graphe passe par une `GraphCommand` exécutée par le `CommandBus`.
5. Le code IA ne modifie jamais le graphe : il produit une `ArchitectureProposal`.
6. Nouveau langage / framework / règle / fournisseur LLM = nouvelle classe enregistrée
   dans un registre, sans modifier le cœur.

## Conventions
- Python 3.11+, typage strict, modèles Pydantic v2, `ruff` + `mypy --strict`, tests `pytest`.
- Ids de nœuds stables : `<type>:<chemin>::<nom qualifié>`, le chemin étant toujours relatif à
  la racine du projet — analyser un sous-dossier ne doit pas renommer les nœuds.
- Noms de classes et de méthodes identiques à ceux des diagrammes UML ; si un écart est
  nécessaire, mettre à jour le diagramme dans le même commit.
- Une décision structurante du développement de SAKG = une ADR dans `docs/adr/`
  (à ne pas confondre avec `.architect/decisions/`, qui contient les ADR des projets analysés).

## Portée du MVP
Parser Python uniquement, persistance JSON dans `.architect/`, CLI Typer, génération
Mermaid (vue CLASS), requêtes dependencies/dependents, analyse d'impact BFS bornée.
Ne pas implémenter PostgreSQL, Web UI ou multi-langage avant validation du MVP.

## Commandes
```bash
pip install -e ".[dev]"
pytest
ruff check . && mypy src
```
