# ARCHITECTURE — SAKG

Version du document : 0.1 · Statut : conception

## 1. Principes directeurs

1. **Le graphe est la source de vérité.** Diagrammes, documentation et réponses de l'IA sont
   des *vues* calculées depuis le graphe, jamais l'inverse.
2. **Toute information a une provenance.** Pas de nœud ni de relation sans `Provenance`
   (type de preuve, confiance, méthode, fichier/ligne, version).
3. **L'IA lit le graphe, elle ne l'écrit pas directement.** Elle produit des
   `ArchitectureProposal` qu'un humain accepte ou rejette ; seule l'acceptation modifie le graphe.
4. **Le domaine ne dépend de rien.** Le cœur (`domain`, `graph`) n'importe ni Tree-sitter,
   ni FastAPI, ni un SDK LLM, ni une base de données.
5. **Extensible par plugins.** Ajouter un langage, un framework, une règle ou un fournisseur LLM
   ne doit pas toucher au cœur.

## 2. Vue en couches (architecture hexagonale)

```
┌──────────────────────────────────────────────────────────────┐
│ INTERFACES (adaptateurs entrants)                            │
│   CLI (Typer) · Serveur MCP · API REST (FastAPI) · Web UI    │
└───────────────────────────┬──────────────────────────────────┘
                            │ appelle uniquement
┌───────────────────────────▼──────────────────────────────────┐
│ APPLICATION                                                  │
│   ArchitectureService (façade) · Commandes · EventBus        │
└──────┬──────────────┬──────────────┬──────────────┬──────────┘
       │              │              │              │
┌──────▼─────┐ ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼────────┐
│ REVERSE    │ │ ANALYSIS &  │ │ GENERATION │ │ AI           │
│ ENGINEERING│ │ VALIDATION  │ │            │ │ AIArchitect  │
└──────┬─────┘ └──────┬──────┘ └─────┬──────┘ └─────┬────────┘
       └──────────────┴──────┬───────┴──────────────┘
┌────────────────────────────▼─────────────────────────────────┐
│ CŒUR : DOMAIN + KNOWLEDGE GRAPH                              │
│   Node · Edge · Provenance · Ontology · KnowledgeGraph       │
│   GraphQueryEngine · Snapshots          ── ports (interfaces)│
└────────────────────────────┬─────────────────────────────────┘
                             │ implémentés par
┌────────────────────────────▼─────────────────────────────────┐
│ INFRASTRUCTURE (adaptateurs sortants)                        │
│   JsonGraphRepository · PostgresGraphRepository              │
│   TreeSitter · Anthropic/OpenAI/Local · FileSystem           │
└──────────────────────────────────────────────────────────────┘
```

**Règle de dépendance :** les flèches pointent vers le cœur. Une règle `LayerDependencyRule`
de SAKG sera appliquée à SAKG lui-même (dogfooding).

## 3. Modèle du graphe

### 3.1 Définition

`G = (V, E)` avec :

- `V` : nœuds typés (`NodeType`), identifiés par un `id` stable
  (ex. `class:src/payment/service.py::PaymentService`)
- `E` : relations typées (`RelationType`) orientées `source → target`
- chaque élément porte une `Provenance`

### 3.2 Ontologie (types de nœuds)

| Niveau | Types |
|---|---|
| Fonctionnel | Project, Requirement, Actor, UseCase, BusinessRule, Constraint |
| Architecture | System, Subsystem, Module, Component, Service, Layer, Package |
| Code | Class, Interface, Function, Method, File, Directory |
| API | Endpoint, Request, Response, Event, Message |
| Données | Database, Schema, Table, Column, Index |
| Infrastructure | Container, Image, Network, Volume, CloudService, Deployment |
| Qualité | Test, TestSuite, Finding, ArchitectureViolation |
| Décision | Technology, ADR, Alternative, TradeOff |

> `Variable`, `Bug`, `Vulnerability` et `Server` sont volontairement repoussés après le MVP
> pour garder un graphe lisible.

### 3.3 Relations et contraintes d'ontologie

`OntologySchema` déclare les triplets autorisés ; toute relation hors schéma est rejetée.

| Relation | Source → Cible |
|---|---|
| `realized_by` | Requirement → UseCase |
| `constrained_by` | Requirement → Constraint |
| `used_by` | UseCase → Actor |
| `implemented_by` | UseCase → Component · Endpoint → Method · Endpoint → Function |
| `contains` | Component → Class · File → Class · File → Function · Class → Method · Table → Column · File → Container |
| `depends_on` | Component → Component · Class → Class · File → File · File → Class, Function (import nommé) · Container → Container · Requirement → Requirement |
| `inherits` / `implements` | Class → Class / Class → Interface |
| `calls` | Method → Method · Method → Function · Function → Function · Function → Method |
| `exposes` | Component → Endpoint · File → Endpoint |
| `maps_to` | Class → Table |
| `reads_from` / `writes_to` | Class → Table |
| `references` | Column → Column (clé étrangère) |
| `verifies` / `tests` | Test → Requirement / Test → Class, Endpoint |
| `deployed_in` | Component → Container |
| `decided_by` | Technology → ADR |
| `uses_technology` | Component → Technology · Container → Technology (image) |
| `belongs_to` | Component, Module, Package → Layer (utilisée par `LayerDependencyRule`) |

Les noms en `snake_case` ci-dessus correspondent aux valeurs de `RelationType` ; les types
de nœuds du §3.2 correspondent un à un à `NodeType` (`UseCase` → `USE_CASE`, etc.).

### 3.4 Provenance

```yaml
provenance:
  evidence_type: OBSERVED      # OBSERVED | INFERRED | GENERATED | USER_DEFINED | RECOMMENDED
  confidence: 1.0              # 0.0 → 1.0
  detected_by: AST_IMPORT_ANALYSIS
  evidence:
    file: src/payment/controller.py
    line: 42
  graph_version: 27
  commit_sha: a1b2c3d
```

Barème de confiance initial (à calibrer expérimentalement) :

| Type | Confiance typique | Exemple |
|---|---|---|
| OBSERVED | 1.0 | import, héritage, décorateur `@app.post` |
| USER_DEFINED | 1.0 | exigence saisie par l'utilisateur |
| INFERRED | 0.5–0.9 | appel dynamique résolu par heuristique, classe ↔ table par convention de nom |
| GENERATED | 0.3–0.8 | composant proposé par le LLM depuis une idée |
| RECOMMENDED | n/a | suggestion, jamais considérée comme un fait |

## 4. Modules

### 4.1 `domain` et `graph` (cœur)

- `Node`, `Edge`, `Provenance`, `Evidence` : modèles Pydantic immuables
- `KnowledgeGraph` : agrégat ; garantit l'unicité des ids et le respect de l'ontologie
- `GraphQueryEngine` : `find`, `dependencies`, `dependents`, `path`, `subgraph` ;
  les traversées sont des `TraversalStrategy` interchangeables
- `GraphSnapshot` : état figé + hash + commit ; base du diff et de l'historique
- Port `GraphRepository` : `save`, `load`, `list_snapshots`, `load_snapshot`

### 4.2 `reverse` (reverse engineering)

Pipeline :

```
ProjectScanner ─► ProjectContext ─► [Extractor₁ … Extractorₙ] ─► GraphBuilder ─► KnowledgeGraph
                                      │
                                      └─ utilisent ParserRegistry ─► LanguageParser (Tree-sitter)
```

- `LanguageParser` : un par langage ; `TreeSitterParser` fournit le squelette commun
  (Template Method), les sous-classes fournissent la grammaire et les requêtes
- Extracteurs indépendants et ordonnés : `CodeStructureExtractor`, `ApiExtractor`,
  `DatabaseExtractor`, `InfrastructureExtractor`, `TestExtractor`
- `FrameworkAdapter` : FastAPI, Django, Express… (détection d'endpoints, d'ORM)
- Chaque extracteur renvoie un `ExtractionResult` (nœuds, relations, avertissements) ;
  `GraphBuilder` fusionne, dédoublonne et résout les références entre fichiers

### 4.3 `analysis`

- `ImpactAnalyzer` : localise les nœuds concernés par un `ChangeRequest`
  (recherche lexicale + sémantique), puis propage via `TraversalStrategy`
  (BFS borné, ou propagation pondérée par type de relation et confiance)
  → `ImpactReport` groupé par niveau (exigences, composants, classes, API, tables, tests)
- `GraphDiffer` : `ArchitectureDiff` (ajouts, suppressions, modifications) entre deux snapshots
- `DriftDetector` : compare `G_a` (architecture documentée/voulue) et `G_c` (extraite du code)
- `MetricsCalculator` : couplage (Ca, Ce, instabilité), cohésion, cycles, fan-in/fan-out
- `ReconstructionEvaluator` : compare un graphe extrait à une vérité terrain
  → `EvaluationReport` (précision, rappel, dérive, calibration ; voir §8)

### 4.4 `validation`

- `ArchitectureRule` (interface) → `check(graph) -> list[Finding]`
- Règles initiales : `LayerDependencyRule`, `NoCycleRule`, `TraceabilityRule`
  (toute exigence a au moins un test), `OrphanComponentRule`
- Règles déclaratives dans `.architect/rules/*.yaml`, chargées par `RuleLoader`

### 4.5 `generation`

- `DiagramGenerator` (interface) : `MermaidGenerator`, `PlantUmlGenerator`
- `DiagramView` : CLASS, USE_CASE, SEQUENCE, COMPONENT, DEPLOYMENT, ERD
- Chaque vue = une **projection** (filtre de types de nœuds/relations) + un rendu
- `DocumentationGenerator` : spécification technique Markdown, index des ADR

### 4.6 `ai`

- `LLMProvider` (interface) + `LLMProviderFactory` : fournisseur choisi par configuration
- `GraphToolkit` : outils exposés au LLM (**lecture seule**) — mêmes fonctions que le MCP
- `AIArchitect` :
  - `design_from_idea(idea)` → `ArchitectureProposal` (nœuds GENERATED)
  - `explain(question)` → réponse fondée sur des appels d'outils au graphe, avec ids cités
  - `propose_change(change)` → impact + proposition
- `ProposalValidator` : couche anti-corruption ; valide la sortie du LLM contre l'ontologie
  (schéma Pydantic) avant toute proposition

### 4.7 `application`

- `ArchitectureService` : façade unique utilisée par CLI, MCP et API
- Mutations = `GraphCommand` (`AddNodeCommand`, `AddEdgeCommand`, `ApplyProposalCommand`)
  exécutées par `CommandBus` → journal, annulation, création de snapshot
- `EventBus` : `GraphChanged`, `ProposalCreated`, `ValidationCompleted`
  (régénération des diagrammes, invalidation de cache)

### 4.8 `interfaces`

| Interface | Rôle |
|---|---|
| CLI `sakg` | usage local et CI — commandes listées dans `docs/uml/use-case-diagram.md` §3 |
| Serveur MCP | outils pour Claude Code / Cursor / Codex |
| API REST | Web UI future, intégrations |

Outils MCP (MVP en lecture) : `get_architecture`, `search_architecture`, `get_node`,
`get_dependencies`, `get_dependents`, `calculate_impact`, `validate_architecture`,
`generate_diagram`. En écriture (phase 2) : `propose_change` — jamais d'écriture directe.

## 5. Flux principaux

### 5.1 Reverse engineering

```
CLI sakg reverse
 → ArchitectureService.reverse(path)
   → ProjectScanner.scan(path) → ProjectContext
   → ReverseEngineeringPipeline.run(context)
       → chaque Extractor.extract(context, registry) → ExtractionResult
       → GraphBuilder.add(…).resolve_references().build() → KnowledgeGraph
   → CommandBus.execute(ReplaceObservedLayerCommand)
   → GraphRepository.save() + snapshot
   → EventBus.publish(GraphChanged)
```

Note : un reverse **remplace uniquement la couche OBSERVED/INFERRED** ; les nœuds
USER_DEFINED (exigences, ADR) sont conservés et re-reliés.

### 5.2 Changement assisté par IA

```
Développeur : "Ajouter les paiements mobiles"
 → ImpactAnalyzer.analyze() → ImpactReport
 → AIArchitect.propose_change() → ArchitectureProposal (status = PROPOSED)
 → ProposalValidator.validate()
 → humain : accept / reject
 → si accept : ApplyProposalCommand → snapshot vN+1
 → implémentation par l'agent de code
 → sakg validate : DriftDetector(G_a = vN+1, G_c = reverse du code)
```

## 6. Patterns utilisés

| Pattern | Où | Pourquoi |
|---|---|---|
| Architecture hexagonale (Ports & Adapters) | global | cœur indépendant des outils |
| Couches (Layered) | global | séparation des responsabilités |
| Repository | `GraphRepository` | JSON aujourd'hui, PostgreSQL demain |
| Strategy | `TraversalStrategy`, `ArchitectureRule` | algorithmes interchangeables |
| Template Method | `TreeSitterParser` | squelette de parsing commun |
| Visitor | parcours d'AST | extraire symboles sans modifier l'AST |
| Registry / Plugin | `ParserRegistry`, extracteurs, règles | extensibilité |
| Pipeline / Chain | `ReverseEngineeringPipeline` | extracteurs ordonnés et isolés |
| Adapter | `FrameworkAdapter`, `LLMProvider` | normaliser des API externes |
| Factory | `LLMProviderFactory` | choix du fournisseur par config |
| Builder | `GraphBuilder` | construction et fusion incrémentales |
| Command | `GraphCommand`, `CommandBus` | journal, annulation, traçabilité |
| Memento / Snapshot | `GraphSnapshot` | versionnement et diff |
| Observer / Event bus | `EventBus` | réactions découplées |
| Facade | `ArchitectureService` | une porte d'entrée pour toutes les interfaces |
| Specification | règles de validation | règles déclaratives composables |
| Anti-Corruption Layer | `ProposalValidator` | isoler le graphe des sorties LLM |
| CQRS léger | requêtes vs commandes | lectures libres, écritures contrôlées |
| Human-in-the-loop | propositions | l'IA propose, l'humain dispose |
| GraphRAG / Tool use | `GraphToolkit` | réponses fondées sur le graphe |

**À explorer (recherche) :** Event Sourcing pour l'historique complet, modèle de provenance
inspiré de W3C PROV, alignement d'ontologie avec C4 et ArchiMate, embeddings de nœuds pour
la recherche sémantique.

## 7. Persistance

- **MVP :** `.architect/graph/nodes.json` et `edges.json` (diffables dans Git, lisibles par les agents)
- **Phase 2 :** PostgreSQL — tables `nodes(id, type, name, properties JSONB, provenance JSONB, version)`
  et `edges(id, source_id, target_id, relation, provenance JSONB, version)` ;
  index sur `type`, `relation`, `(source_id, relation)`, `(target_id, relation)`
- Une base graphe (Neo4j) n'est pas exclue, mais n'est pas nécessaire tant que les
  traversées se font en mémoire avec NetworkX.

## 8. Évaluation scientifique

| Métrique | Définition |
|---|---|
| Précision / rappel de reconstruction | sur nœuds et relations, vs vérité terrain annotée |
| Cohérence | relations correctes / relations attendues |
| Dérive | `Drift(G_a, G_c) = 1 − |E_a ∩ E_c| / |E_a ∪ E_c|` (distance de Jaccard sur les relations) |
| Impact | précision/rappel des composants prédits vs réellement modifiés dans l'historique Git |
| Calibration | confiance déclarée vs taux réel d'exactitude par `EvidenceType` |

Protocole envisagé : projets open source annotés ; comparer (a) documentation existante,
(b) LLM seul sur le code, (c) SAKG, (d) LLM + SAKG via outils.

## 9. Risques et décisions ouvertes

- **Portée :** le projet est très large ; le MVP doit rester Python + JSON + CLI + Mermaid.
- **Appels dynamiques** (injection de dépendances, réflexion) : relations INFERRED à
  confiance réduite, à mesurer.
- **Identité stable des nœuds** après renommage/déplacement : stratégie de rapprochement à définir.
- **Taille des graphes** : prévoir des vues filtrées pour les diagrammes et le MCP.
- ADR à rédiger : ADR-001 JSON puis PostgreSQL · ADR-002 NetworkX · ADR-003 Tree-sitter ·
  ADR-004 écriture IA uniquement via propositions.
