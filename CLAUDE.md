@AGENTS.md

## Skills du projet (`.claude/skills/`)

Installés avec `npx skills add … --agent claude-code --copy` ; versions figées dans
`skills-lock.json` (restauration : `npx skills experimental_install`).

### 1. Conception et structure
| Skill | Usage dans SAKG |
|---|---|
| `python-project-structure` | mise en place de `src/sakg/` (domain, graph, reverse…), `__all__`, API publique des modules |
| `python-design-patterns` | patterns de `docs/ARCHITECTURE.md` §6 (Strategy, Repository, Command…), séparation cœur / adaptateurs |

### 2. Implémentation
| Skill | Usage dans SAKG |
|---|---|
| `python-code-style` | conventions `ruff` + `mypy --strict`, nommage, docstrings |
| `fastapi-python` | `interfaces/api/` (API REST) — hors MVP |
| `python-performance-optimization` | traversées NetworkX et reverse sur gros dépôts — après mesure, hors MVP |

### 3. Qualité et revue
| Skill | Usage dans SAKG |
|---|---|
| `requesting-code-review` | à la fin d'une tâche ou d'une fonctionnalité, avant fusion |
| `code-review` | revue d'une branche en deux axes : standards (`AGENTS.md`) et spécification (`docs/`) |
| `refactor` | refactorisations sans changement de comportement ; mettre à jour les diagrammes UML dans le même commit |

> `code-review` (mattpocock/skills) porte le même nom que la commande intégrée `/code-review`
> de Claude Code, qui cherche des bugs. Préciser lequel utiliser.

### 4. Planification
| Skill | Usage dans SAKG |
|---|---|
| `sprint-planning` | découper la feuille de route du `README.md` (MVP → MCP) en sprints |
