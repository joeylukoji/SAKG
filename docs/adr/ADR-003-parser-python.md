# ADR-003 — Parser Python : `ast` pour le MVP, Tree-sitter pour le multi-langage

- **Statut :** accepté
- **Date :** 2026-09-17
- **Concerne :** `src/sakg/reverse/`, sprint S3

## Contexte

`docs/ARCHITECTURE.md` §4.2 prévoit `TreeSitterParser` comme squelette commun de parsing
(Template Method), les sous-classes fournissant grammaire et requêtes. La portée du MVP
(`AGENTS.md`) se limite pourtant au **parser Python**.

Vérification faite en début de sprint : `tree-sitter` 0.26 et `tree-sitter-python`
s'installent sans difficulté sous Windows en Python 3.13. Le risque « wheels » du plan de
sprint est donc levé ; le choix se fait sur d'autres critères.

## Décision

Pour le MVP, `PythonAstParser` s'appuie sur le module **`ast` de la bibliothèque standard**.
`TreeSitterParser` est reporté à la phase multi-langage (TypeScript, Go).

Les deux implémentent la même interface `LanguageParser` et s'enregistrent dans
`ParserRegistry` : le reste du pipeline ignore la technologie de parsing.

## Justification

| Critère | `ast` | Tree-sitter |
|---|---|---|
| Portées et noms qualifiés | natifs (`ClassDef`, `FunctionDef` imbriqués) | à reconstruire depuis l'arbre concret |
| Imports relatifs (`from . import x`) | niveau fourni par le nœud `ImportFrom` | à analyser à la main |
| Dépendance | aucune (stdlib) | binaire natif + grammaire par langage |
| Quantité de code pour le MVP | faible | requêtes à écrire et à maintenir |
| Multi-langage | impossible | c'est son intérêt principal |
| Code invalide syntaxiquement | échec, signalé en avertissement | analyse partielle tolérante |

Le seul avantage perdu au MVP est la tolérance aux fichiers non analysables : le pipeline les
signale dans `ExtractionResult.warnings` au lieu de les analyser partiellement, ce qui est
acceptable pour un dépôt qui compile.

## Conséquences

- `docs/uml/class-diagram.md` §2 montre `PythonAstParser` sous `LanguageParser`,
  `TreeSitterParser` restant prévu pour la phase 7.
- Aucune dépendance supplémentaire dans `pyproject.toml` au MVP.
- Ajouter TypeScript ou Go impliquera d'introduire `TreeSitterParser` sans toucher au cœur
  ni aux extracteurs (règle 6 d'`AGENTS.md`).
