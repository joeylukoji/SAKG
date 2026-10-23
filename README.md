# SAKG — Software Architecture Knowledge Graph

[![CI](https://github.com/joeylukoji/SAKG/actions/workflows/ci.yml/badge.svg)](https://github.com/joeylukoji/SAKG/actions/workflows/ci.yml)
[![Licence : MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)

> Une représentation sémantique, versionnée et traçable de l'architecture d'un logiciel,
> sur laquelle humains et agents IA (Claude Code, Cursor, Codex) raisonnent au lieu de deviner.

SAKG construit un **graphe de connaissances architectural** qui relie exigences, cas d'utilisation,
composants, classes, API, tables, tests, infrastructure et décisions d'architecture (ADR).
Le graphe est la **source de vérité architecturale** : les diagrammes, la documentation, l'analyse
d'impact et la détection de dérive en sont tous dérivés.

```
 Idée / Exigences ──┐                         ┌── Diagrammes (Mermaid, PlantUML)
                    ├──► KNOWLEDGE GRAPH ◄────┼── Analyse d'impact
 Code source ───────┘   (nœuds + relations    ├── Validation / dérive
  (reverse eng.)         + provenance)        └── Agents IA via MCP
```

---

## Pourquoi

L'architecture d'un projet est habituellement dispersée (README, UML, code, migrations, Docker,
ADR…) et ces sources divergent vite. Les agents de code, eux, ne voient que des fichiers.
SAKG unifie ces sources dans un modèle unique `G = (V, E)` où **chaque relation porte sa preuve**
(fichier, ligne, méthode de détection, niveau de confiance, version).

## Fonctionnalités visées

| Domaine | Capacité |
|---|---|
| Reverse engineering | Extraire classes, dépendances, endpoints, tables et conteneurs depuis le code |
| Knowledge Graph | Nœuds/relations typés selon une ontologie, provenance, confiance, versions |
| Raisonnement | Dépendances, dépendants, chemins, sous-graphe d'impact |
| Validation | Règles d'architecture (couches, cycles, traçabilité), dérive documenté ↔ code |
| Évolution | Snapshots, diff entre versions, ADR reliées aux composants |
| Génération | Diagrammes de classes, cas d'utilisation, séquence, composants, ERD |
| IA | Conception depuis une idée, explication, proposition de changement (validée par un humain) |
| Intégration | CLI, serveur MCP, API REST |

## Démarrage rapide

```bash
git clone https://github.com/joeylukoji/SAKG.git && cd SAKG
pip install -e ".[dev]"
sakg init                              # crée .architect/ et project.yaml
sakg reverse                           # reconstruit le graphe depuis les source_roots
sakg query KnowledgeGraph --dependents # recherche, dépendances, dépendants
sakg query --type endpoint             # inventaire : routes, tables, conteneurs…
sakg impact "Ajouter les paiements mobiles"
sakg uml --view class                  # écrit .architect/diagrams/class.md
sakg history                           # versions archivées du graphe
sakg diff 3 4                          # ce qui a changé dans l'architecture
sakg validate                          # règles d'architecture (.architect/rules/*.yaml)
sakg drift                             # dérive entre le graphe enregistré et le code
```

Prévues par la feuille de route (voir [Tâches ouvertes](#tâches-ouvertes)) :

```bash
sakg ask "pourquoi ce composant ?"   # explication fondée sur le graphe
sakg mcp                             # expose le graphe aux agents IA
```

SAKG s'applique à lui-même : `sakg reverse` sur ce dépôt produit 546 nœuds et 1 323 relations,
et `sakg validate` vérifie les règles d'[`AGENTS.md`](AGENTS.md) sur son propre code.

Liste complète des commandes (`design`, `change`, `proposal`, `docs`, `adr`, `ask`,
`requirement`, `eval`…) : [`docs/uml/use-case-diagram.md`](docs/uml/use-case-diagram.md) §3.

> Le document de conception mentionnait aussi le nom `sako` : le nom retenu ici est **`sakg`**
> pour le paquet et la CLI.

## Le dossier `.architect/`

L'architecture voyage avec le code :

```
.architect/
├── project.yaml          # métadonnées, langages, règles actives
├── graph/                # nodes.json, edges.json, meta.json (état courant)
├── versions/             # snapshots historiques
├── decisions/            # ADR-XXX.md
├── rules/                # règles d'architecture (YAML)
├── diagrams/             # diagrammes générés (Mermaid)
├── proposals/            # propositions de changement en attente de validation
└── audit/                # rapports de validation et de dérive
```

## Stack technique (prototype)

- **Python 3.11+**, Pydantic v2 (modèle et validation), Typer (CLI), PyYAML (configuration),
  FastAPI (API REST, hors MVP)
- **Tree-sitter** (parsing multi-langage), **NetworkX** (graphe en mémoire)
- Persistance : **JSON** pour le MVP, **PostgreSQL + JSONB** ensuite
- Diagrammes : **Mermaid** d'abord, PlantUML ensuite
- IA : abstraction de fournisseur (Anthropic, OpenAI, Google, modèles locaux)
- Intégration agents : **MCP** (Model Context Protocol)

## Structure du dépôt

```
sakg/
├── AGENTS.md              # règles d'architecture et conventions (humains et agents IA)
├── CONTRIBUTING.md        # comment prendre une tâche et ouvrir une PR
├── CLAUDE.md              # configuration d'agent : skills du projet par catégorie
├── skills-lock.json       # skills d'agents (restauration : npx skills experimental_install)
├── src/sakg/
│   ├── domain/            # Node, Edge, Provenance, ontologie — aucune dépendance externe
│   ├── graph/             # KnowledgeGraph, requêtes, traversées, snapshots
│   ├── reverse/           # parsers, extracteurs, pipeline de reverse engineering
│   ├── analysis/          # impact, diff, dérive, métriques
│   ├── validation/        # règles d'architecture
│   ├── generation/        # diagrammes, documentation
│   ├── ai/                # fournisseurs LLM, AIArchitect, outils sur le graphe
│   ├── application/       # ArchitectureService (façade), commandes, événements
│   ├── infrastructure/    # repositories JSON / PostgreSQL, config
│   └── interfaces/        # cli/, mcp/, api/
├── tests/
└── docs/                  # ARCHITECTURE.md, uml/, adr/, sprints/, EVOLUTION.md
```

## Feuille de route et avancement

| # | Phase | État |
|---|---|---|
| 1 | **MVP** — ontologie, graphe, provenance, parser Python, JSON, CLI, diagramme de classes Mermaid, requêtes, impact BFS borné | ✅ fait (S0–S5) |
| 2 | **Reverse engineering** — endpoints FastAPI, modèles SQLAlchemy, docker-compose | ✅ fait (S6–S7) |
| 3 | **Raisonnement** — diff, historique des snapshots, impact pondéré | 🟡 diff et historique faits (S8) ; impact pondéré à faire |
| 4 | **Validation** — règles, dérive, rapports | 🟡 règles de couches et de cycles, dérive faites (S9) ; CI et règles de traçabilité à faire |
| 5 | **IA** — conception depuis une idée, explication, propositions validées | ⬜ à faire (`src/sakg/ai/` est vide) |
| 6 | **MCP** — outils en lecture, puis écriture via propositions | ⬜ à faire |
| 7 | **Multi-langage & intégrations IDE** — TypeScript, JavaScript, Go… | 🟡 TypeScript et Next.js (Route Handlers) faits ; le reste à faire |

Détail sprint par sprint : [`docs/sprints/PLAN.md`](docs/sprints/PLAN.md) ;
journal de ce qui a été livré : [`docs/EVOLUTION.md`](docs/EVOLUTION.md).

## Tâches ouvertes

Chaque tâche est indépendante sauf mention dans « Dépend de ».

> **Avant de travailler sur une tâche**, ouvrez une PR de proposition (brouillon) intitulée
> `[Proposition] Txx — <titre>` qui explique ce que vous voulez faire. **Vous ne commencez à
> coder qu'après l'approbation du mainteneur** : c'est ce qui garantit que personne ne
> travaille sur une partie déjà prise. Une tâche citée par une PR ouverte est déjà prise.
> Détails : [`CONTRIBUTING.md`](CONTRIBUTING.md#prendre-une-tâche).

Difficulté : 🟢 facile (≤ ½ jour) · 🟡 moyenne (1–2 jours) · 🔴 difficile (plusieurs jours).

### A. Dette du raisonnement et de la validation (prochain sprint, S10)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T01 | Brancher `sakg validate` et `sakg drift` dans la CI (`.github/workflows/ci.yml`) | CI | 🟢 | — |
| T02 | Mots vides et seuils de correspondance de l'impact : les lire dans `project.yaml` au lieu du code | `analysis`, `infrastructure` | 🟢 | — |
| T03 | Recaler `Provenance.graph_version` sur la version du snapshot enregistré | `application` | 🟢 | — |
| T04 | Politique de rétention de `.architect/versions/` (garder les N dernières) | `infrastructure` | 🟢 | — |
| T05 | `OntologySchema.load(path)` depuis YAML (reporté depuis S1) | `domain` | 🟢 | — |
| T06 | Impact pondéré : `WeightedPropagationStrategy` (reporté depuis S8) | `analysis` | 🟡 | — |
| T07 | Vue CLASS : remonter les `depends_on` entre fichiers aux classes | `generation` | 🟡 | — |
| T08 | `MetricsCalculator` (cycles, couplage, centralité) ; `NoCycleRule` lui délègue | `analysis`, `validation` | 🟡 | — |
| T09 | `TraceabilityRule` et `OrphanComponentRule` (ARCHITECTURE §4.4) | `validation` | 🟡 | — |
| T10 | Recherche sémantique des points de départ de l'impact (ARCHITECTURE §4.3) | `analysis` | 🔴 | T11 |

### B. IA (phase 5, S10–S11)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T11 | Abstraction `LLMProvider` + registre de fournisseurs (Anthropic, OpenAI, local) | `ai` | 🟡 | — |
| T12 | `ArchitectureProposal` : stockage dans `.architect/proposals/`, `sakg proposal list/accept/reject` (UC06, UC07) | `application`, `interfaces` | 🟡 | — |
| T13 | `sakg ask` : expliquer l'architecture à partir du graphe (UC14) | `ai`, `interfaces` | 🟡 | T11 |
| T14 | `AIArchitect` : concevoir une architecture depuis une idée, sous forme de proposition (UC03, ADR-004) | `ai` | 🔴 | T11, T12 |
| T15 | Enregistrer une ADR reliée aux composants : `sakg adr` (UC13) | `application`, `interfaces` | 🟡 | — |

### C. MCP (phase 6, S12)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T16 | Serveur MCP en lecture : `query`, `impact`, `uml`, `validate` | `interfaces/mcp` | 🟡 | — |
| T17 | Écriture via MCP, uniquement par propositions | `interfaces/mcp` | 🟡 | T12, T16 |

### D. Reverse engineering : cas non couverts (S13)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T18 | Routes déclarées par `add_api_route` | `reverse` | 🟢 | — |
| T19 | `Mapped[int]` sans appel (SQLAlchemy 2.0) déclare une colonne | `reverse` | 🟢 | — |
| T20 | `include_router` appelé dans une fabrique (`create_app()`) : appliquer le préfixe | `reverse` | 🟡 | — |
| T21 | `OrmAdapter` sur le modèle de `FrameworkAdapter` : SQLModel, Flask-SQLAlchemy | `reverse` | 🟡 | — |
| T22 | Colonnes héritées d'un mixin ou d'une classe parente | `reverse` | 🟡 | — |
| T23 | Numéros de ligne dans la provenance des nœuds d'infrastructure | `reverse` | 🟡 | — |
| T24 | Fusion des fichiers `docker-compose.override.yml` | `reverse` | 🟡 | — |
| T25 | Appels au niveau module (`CallSite`) : produire des relations | `reverse` | 🟡 | — |
| T26 | `EndpointSpec.handler` qualifié hors du module courant | `reverse` | 🔴 | — |

### E. Multi-langage et frameworks (phase 7)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T27 | Parser JavaScript (`.js`/`.jsx`, aujourd'hui simples fichiers d'inventaire) | `reverse` | 🟡 | — |
| T28 | `ExpressAdapter` | `reverse` | 🟡 | T26, T27 |
| T29 | `DjangoAdapter` | `reverse` | 🟡 | T26 |
| T30 | Pages Next.js (`page.tsx`) : routage UI | `reverse` | 🟡 | — |
| T31 | Parsers Go, Java, Kotlin, C#, PHP, Ruby, Dart (un par contributeur) | `reverse` | 🟡 | — |

### F. Génération, persistance, recherche (après validation de la phase 5)

| Id | Tâche | Module | Diff. | Dépend de |
|---|---|---|---|---|
| T32 | Vues Mermaid : composants, séquence, cas d'utilisation, ERD (UC11) | `generation` | 🟡 | — |
| T33 | Génération de documentation : `sakg docs` (UC12) | `generation` | 🟡 | — |
| T34 | Exigences et règles saisies par l'utilisateur : `sakg requirement` (UC15) | `application`, `interfaces` | 🟡 | — |
| T35 | Évaluation de la reconstruction : précision/rappel, `sakg eval` (UC16) | `analysis` | 🔴 | — |
| T36 | Export PlantUML | `generation` | 🟢 | — |
| T37 | Dépôt PostgreSQL + JSONB derrière `GraphRepository` | `infrastructure` | 🔴 | — |
| T38 | API REST (FastAPI) | `interfaces/api` | 🟡 | — |

## Question de recherche

> Un Knowledge Graph architectural unifié améliore-t-il la reconstruction, la compréhension et
> l'évolution cohérente d'une architecture logicielle, par rapport à une documentation classique
> ou à une génération directement produite par un LLM ?

Métriques : précision/rappel de reconstruction, cohérence, dérive `Drift(G_a, G_c)`,
exactitude de l'analyse d'impact. Détails dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture détaillée et patterns
- [`docs/uml/class-diagram.md`](docs/uml/class-diagram.md) — diagrammes de classes (Mermaid)
- [`docs/uml/use-case-diagram.md`](docs/uml/use-case-diagram.md) — cas d'utilisation (Mermaid)
- [`docs/adr/`](docs/adr/) — décisions d'architecture (persistance, NetworkX, parser, IA, hash)
- [`docs/sprints/PLAN.md`](docs/sprints/PLAN.md) — découpage en sprints, avancement et dette
- [`docs/EVOLUTION.md`](docs/EVOLUTION.md) — journal de ce qui a été livré
- [`AGENTS.md`](AGENTS.md) — règles d'architecture et conventions
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — comment contribuer

## Contribuer

Les contributions sont bienvenues :

1. choisir une tâche libre dans [Tâches ouvertes](#tâches-ouvertes) ;
2. ouvrir une PR **brouillon** `[Proposition] Txx — <titre>` qui décrit ce que vous voulez faire ;
3. attendre l'approbation du mainteneur, **puis seulement** coder dans cette même PR ;
4. suivre [`CONTRIBUTING.md`](CONTRIBUTING.md) (environnement, règles d'architecture, Definition of Done).

## Licence

[MIT](LICENSE)
