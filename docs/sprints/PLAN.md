# Plan de sprints — SAKG

Produit avec le skill `sprint-planning`. Source du backlog : `README.md` (feuille de route),
`docs/ARCHITECTURE.md`, `docs/uml/`, `AGENTS.md` (portée du MVP).

## Hypothèses de capacité

| Paramètre | Valeur |
|---|---|
| Équipe | 1 développeur |
| Durée d'un sprint | 1 semaine (5 jours) |
| Capacité | 20 points par sprint |
| Charge planifiée | ≈ 16 points (80 %, marge pour imprévus) |
| Échelle | 1 pt ≈ 2 h · 2 pts ≈ demi-journée · 3 pts ≈ journée · 5 pts ≈ 2 jours |

À ajuster après le sprint 1 selon la vélocité réelle.

## Avancement

| Sprint | Statut | Notes |
|---|---|---|
| S0 | ✅ terminé | venv Python 3.13, 2 tests d'architecture |
| S1 | ✅ P0 + P1 terminés · P2 (`OntologySchema.load` YAML) reporté | 48 tests ; `NodeResolver` ajouté pour respecter la règle de dépendance |
| S2 | ✅ terminé, revu et corrigé | revue : snapshot qui aliasait le graphe vivant (corrigé par `KnowledgeGraph.copy`), relations USER_DEFINED non re-reliées après reverse (corrigé), isolation des abonnés d'événements |
| S3 | ✅ terminé, revu et corrigé | 144 tests ; parser `ast` au lieu de Tree-sitter ([ADR-003](../adr/ADR-003-parser-python.md)) ; revue : héritage et appels résolus par nom simple produisaient des relations **fausses** en OBSERVED → résolution désormais fondée sur les imports visibles du module ; scan de la racine 1049 ms → 16 ms |
| S4 | ✅ terminé, revu et corrigé | revue : rapport d'impact arbitraire (troncature alphabétique des ex aequo, 34 nœuds pour « support de TypeScript ») et cibles explicites tronquées en silence → pondération des jetons, couverture de la description, avertissements, pas de propagation sur correspondance faible, et le rapport dit *pourquoi* chaque nœud est touché |
| S5 | ✅ terminé, revu et corrigé — **jalon MVP atteint** | 217 tests ; `sakg init/reverse/query/impact/uml/history` sur ce dépôt (331 nœuds, 503 relations) ; ADR-001, 002, 004, 005. Revue : écritures non atomiques (graphe corrompu rechargé en silence) et graphe réécrit intégralement à chaque reverse → écriture atomique + contrôle d'intégrité, provenance conservée à contenu inchangé, aucune version créée sans changement, identifiants indépendants des `source_roots` |
| S6 | ✅ terminé, revu et corrigé | 253 tests ; revue : **chemins d'URL faux** sans avertissement (préfixe dans une variable, alias d'import, montage imbriqué, routeur monté deux fois) → le parser distingue littéral et identifiant, les montages se résolvent par point fixe entre fichiers, et tout ce qui n'est pas traçable devient un avertissement. Endpoints FastAPI (décorateurs, préfixes locaux et `include_router` entre fichiers), `ApiExtractor` + `FrameworkAdapter` ; dette traitée : avertissements retournés par le pipeline, imports `TYPE_CHECKING` marqués `type_only`, parsing mutualisé entre extracteurs |
| S7 | ✅ terminé, revu et corrigé | revue : deux faits faux — une clé étrangère `sales.customers` reliée à `billing.customers` (schéma ignoré) et une colonne nommée d'après l'attribut Python au lieu du nom en base — corrigés, avec vérification que la colonne visée existe ; image `${TAG}` non matérialisée ; périmètre `include` respecté par l'infrastructure. Détail : 275 tests ; `DatabaseExtractor` (modèles SQLAlchemy → tables, colonnes, clés étrangères résolues entre fichiers) et `InfrastructureExtractor` (docker-compose → conteneurs, images, dépendances) ; briques communes des extracteurs extraites dans `reverse/extraction.py` ; `sakg query --type` liste l'inventaire d'un type |
| S8 | ✅ terminé, revu et corrigé | 318 tests ; revue : `sakg diff` annonçait **supprimées** des relations toujours présentes dont seule la nature avait changé (typage → exécution) → relations modifiées distinguées et décrites ; un nom lié à des origines différentes (repli `try/except ImportError`) ou à la fois défini et importé était relié au dernier import, donc parfois à l'implémentation de repli → désormais ambigu, aucune relation, avertissement ; `type_only` des symboles indépendant de l'ordre des imports ; comptes absents d'un ancien `meta.json` affichés « ? » et non « 0 ». Détail : `GraphDiffer` et `sakg diff v1 v2` (changements au sens d'ADR-005) ; historique lu depuis les métadonnées seules ; dépendances au niveau symbole ; **ré-exportations de paquets suivies** : héritages de `SakgError` retrouvés 10/10 au lieu de 6, utilisateurs de `KnowledgeGraph` 14 au lieu de 5 |
| S9 | ✅ P0 + P1 terminés · P2 (impact pondéré) reporté | 376 tests ; `ArchitectureRule`/`Finding`/`Severity`/`ValidationReport`/`ArchitectureValidator`, `LayerDependencyRule`, `NoCycleRule`, `RuleLoader` (`.architect/rules/*.yaml`, registre de types de règles) et `sakg validate` (UC08) ; `DriftDetector` + `sakg drift` (UC09, distance de Jaccard §8), qui recalcule la couche observée sans l'enregistrer pour ne jamais confondre un nœud `USER_DEFINED` avec une dérive. Premier client : `.architect/rules/agents-md.yaml` encode les règles 1 et 2 d'AGENTS.md (couches, cycles) — SAKG se valide lui-même sans violation, 0 % de dérive juste après `sakg reverse`. Détail dans [`docs/EVOLUTION.md`](../EVOLUTION.md) |

Reverse de SAKG par lui-même : 546 nœuds, 1 323 relations (v11, après S9) ; deux exécutions
successives produisent des fichiers identiques au bit près.

### Écart au plan : TypeScript et Next.js anticipés (phase 7, avant S9)

**2026-09-22.** Une partie de la phase 7 (multi-langage, prévue en S13+) a été avancée hors
séquence, avant même S9 (règles et dérive). Détail complet dans
[`docs/EVOLUTION.md`](../EVOLUTION.md). Résumé :

- `TreeSitterParser` (squelette générique, Template Method) + `TypeScriptParser` : classes,
  méthodes, fonctions, imports ESM, appels, héritage (`extends`) ; `EcmaImportResolver` pour
  les imports relatifs (`from "./base"`). `sakg reverse` lit `languages` dans
  `.architect/project.yaml` ; un fichier sans parser devient un nœud `File` d'inventaire, un
  seul avertissement par langage.
- `NextJsAdapter` (nouveau `FrameworkAdapter`, enregistré dans `ApiExtractor` à côté de
  `FastApiAdapter`) : Route Handlers de l'App Router (`app/**/route.ts`). Contrairement à
  FastAPI, aucun décorateur : le verbe HTTP vient du nom de la fonction exportée (`GET`,
  `POST`…), le chemin de l'arborescence (`[id]` → `{id}`, `[...slug]` → `{...slug}`,
  `[[...slug]]` → `{...slug?}`, groupes de routage `(marketing)` ignorés, dossiers privés
  `_lib` hors routage).
- Revue de l'étape : héritage TypeScript jamais détecté (`extends_clause` de Tree-sitter non
  déplié — aucune relation `INHERITS` n'était produite) ; provenance des endpoints codée en dur
  en `PYTHON_AST_*` quel que soit le langage du fichier → les deux corrigés. Un test d'impact
  est devenu faux par la présence même du nouveau code (« TypeScript » n'est plus un mot
  fragmenté sans correspondance dans le graphe de SAKG, il y correspond maintenant pour de
  bon) → remplacé par un exemple qui préserve l'intention du test.
- 340 tests, `ruff check .` et `mypy --strict` verts.

**Reste en dette pour S13+** (complète le tableau ci-dessous) : parser JavaScript (`.js`/`.jsx`
restent de simples fichiers d'inventaire, sans symboles), `ExpressAdapter`, `DjangoAdapter`,
pages Next.js (`page.tsx` — routage UI plutôt qu'endpoint HTTP, volontairement laissé hors de
`ApiExtractor`), Go, Dart, Java, Kotlin, C#, PHP, Ruby.

### Dette identifiée par les revues, à traiter plus tard

| Sujet | Sprint visé |
|---|---|
| Vue CLASS : les `depends_on` entre fichiers ne sont pas remontés aux classes (seuls les appels le sont) | S10 |
| Intégration continue : `sakg drift` existe (S9) mais n'est câblé dans aucun workflow CI | S10 |
| Recherche sémantique des points de départ (ARCHITECTURE §4.3 : lexicale **et** sémantique) | S10 |
| Impact pondéré (`WeightedPropagationStrategy`), prévu en S8, reporté en S9 (P2), toujours pas réalisé | S10 |
| Mots vides et seuils de correspondance figés dans le code, à porter dans `project.yaml` | S10 |
| `NoCycleRule` réimplémente la détection de cycles (`networkx` direct) plutôt que déléguer à `MetricsCalculator.cycles()` (ARCHITECTURE §4.3), qui n'existe pas encore | non planifié |
| `TraceabilityRule` et `OrphanComponentRule` (ARCHITECTURE §4.4), prévues au diagramme, pas implémentées | non planifié |
| Routes déclarées dynamiquement (`add_api_route`) non extraites | S13 |
| `include_router` appelé dans une fabrique (`create_app()`) : préfixe signalé, non appliqué | S13 |
| `OrmAdapter` sur le modèle de `FrameworkAdapter` : SQLModel et Flask-SQLAlchemy (`db.Column`) ne produisent rien | S13 |
| Colonnes déclarées par un mixin ou une classe parente non rattachées à la table | S13 |
| `Mapped[int]` sans appel (SQLAlchemy 2.0) ne déclare aucune colonne | S13 |
| Provenance des nœuds d'infrastructure sans numéro de ligne (`yaml.safe_load` ne les donne pas) | S13 |
| Fichiers `docker-compose.override.yml` non fusionnés (sémantique Docker à reproduire) | S13 |
| `EndpointSpec.handler` n'est qualifié que dans le module courant ; Django/Express déclarent leurs routes ailleurs que leurs vues | S13 |
| Appels au niveau module (`CallSite`) captés mais ne produisant aucune relation | S13 |
| Autres frameworks : `DjangoAdapter`, `ExpressAdapter` (`NextJsAdapter` fait, cf. §Écart au plan) | S13 |
| Parser JavaScript (`.js`/`.jsx` restent des fichiers d'inventaire, sans symboles) | S13 |
| Pages Next.js (`page.tsx`) non modélisées : routage UI, volontairement hors `ApiExtractor` | S13+ |
| `.architect/versions/` n'est pas versionné dans Git (regénérable) ; définir une politique de rétention | S10 |
| `Provenance.graph_version` jamais recalée sur la version du snapshot | S10 |

## Vue d'ensemble

Ordre dicté par la règle de dépendance (les couches externes dépendent du cœur) :

| Sprint | Objectif | Phase feuille de route | Skills principaux |
|---|---|---|---|
| S0 | Fondations du dépôt outillées | MVP | python-project-structure, python-code-style |
| S1 | Cœur du domaine : graphe typé, provenance, ontologie | MVP | python-design-patterns, python-code-style |
| S2 | Persistance JSON, snapshots, commandes et événements | MVP | python-design-patterns |
| S3 | Reverse engineering Python → graphe | MVP | python-design-patterns, python-performance-optimization (mesure seulement) |
| S4 | Requêtes et analyse d'impact BFS bornée | MVP | python-design-patterns |
| S5 | Façade, CLI Typer, diagramme Mermaid, dogfooding | MVP — **jalon MVP** | python-code-style, requesting-code-review |
| S6–S7 | Endpoints FastAPI, SQLAlchemy, docker-compose | 2. Reverse engineering | fastapi-python |
| S8 | Impact pondéré, diff, historique | 3. Raisonnement | python-performance-optimization |
| S9 | Règles, dérive, rapports | 4. Validation | — |
| S10–S11 | AIArchitect, propositions validées | 5. IA | — |
| S12 | Serveur MCP (lecture puis propositions) | 6. MCP | — |
 

Chaque sprint se termine par `requesting-code-review` (revue de la tâche) puis `code-review`
(standards `AGENTS.md` + spécification `docs/`). `refactor` est utilisé en début de sprint
suivant pour traiter les remarques, sans changement de comportement.

---

## Sprint Plan : S0 — Fondations
**Dates :** 2026-09-17 — 2026-09-18 | **Équipe :** 1 dev
**Objectif :** `pip install -e ".[dev]"`, `pytest`, `ruff check` et `mypy --strict` passent sur un squelette vide respectant la structure du README.

### Sprint Backlog
| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | Dépôt git, `.gitignore` | 1 pt | — |
| P0 | `pyproject.toml` (Pydantic, NetworkX, Typer ; dev : pytest, ruff, mypy) | 1 pt | — |
| P0 | Arborescence `src/sakg/{domain,graph,reverse,analysis,validation,generation,ai,application,infrastructure,interfaces}` avec `__init__.py` et `__all__` | 1 pt | — |
| P0 | Configuration ruff (règles du skill) + mypy strict + pytest | 1 pt | pyproject |
| P1 | Test d'architecture : `domain`/`graph` n'importent que stdlib, Pydantic, NetworkX (règle 1 d'`AGENTS.md`) | 2 pts | arborescence |

**Charge :** 6 pts

---

## Sprint Plan : S1 — Cœur du domaine
**Dates :** 2026-09-21 — 2026-09-25
**Objectif :** construire en mémoire un `KnowledgeGraph` dont chaque nœud et relation a une provenance et respecte l'ontologie.

### Sprint Backlog
| Priorité | Élément | Estimation | Dépendances | Réf. |
|---|---|---|---|---|
| P0 | Enums `NodeType`, `RelationType`, `EvidenceType` | 1 pt | S0 | class-diagram §1 |
| P0 | `Evidence`, `Provenance` (immuables, confiance ∈ [0,1], `is_fact()`) | 2 pts | enums | ARCHITECTURE §3.4 |
| P0 | `Node`, `Edge` + convention d'ids `<type>:<chemin>::<nom>` | 2 pts | Provenance | AGENTS.md |
| P0 | `OntologySchema` : triplets autorisés de ARCHITECTURE §3.3 | 3 pts | Node, Edge | ARCHITECTURE §3.3 |
| P0 | `KnowledgeGraph` : ajout/suppression, unicité des ids, extrémités existantes, validation ontologie, `in/out_edges`, `subgraph`, `to_networkx` | 5 pts | OntologySchema | ARCHITECTURE §4.1 |
| P1 | Erreurs du domaine (`DuplicateNodeError`, `OntologyViolationError`…) | 1 pt | KnowledgeGraph | — |
| P2 | `OntologySchema.load(path)` depuis YAML | 2 pts | OntologySchema | — |

**Charge :** 14 pts (P0 + P1), 16 pts avec P2

### Risques
| Risque | Impact | Mitigation |
|---|---|---|
| Ontologie trop stricte pour le reverse (S3) | relations rejetées | tests d'ontologie dès S1 ; ajuster le schéma plutôt que contourner |
| Identité des nœuds après renommage | doublons | hors MVP, noté dans ARCHITECTURE §9 |

---

## Sprint Plan : S2 — Persistance et commandes
**Objectif :** toute mutation passe par `CommandBus`, produit un snapshot versionné et est sauvegardée dans `.architect/graph/`.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | Port `GraphRepository` + `GraphSnapshot` (hash stable) | 2 pts | S1 |
| P0 | `JsonGraphRepository` : `nodes.json`, `edges.json`, `versions/` (JSON trié, diffable) | 3 pts | port |
| P0 | `GraphCommand` + `AddNodeCommand`, `AddEdgeCommand` (execute/undo) | 3 pts | S1 |
| P0 | `CommandBus` : historique, `undo_last`, snapshot après exécution | 3 pts | commandes, repo |
| P1 | `EventBus` + `GraphChanged` | 2 pts | CommandBus |
| P1 | `ReplaceObservedLayerCommand` (conserve USER_DEFINED) | 3 pts | CommandBus |

**Charge :** 16 pts

---

## Sprint Plan : S3 — Reverse engineering Python
**Objectif :** `ReverseEngineeringPipeline.run()` produit un graphe OBSERVED (fichiers, classes, méthodes, fonctions, héritage, imports) d'un projet Python.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `ProjectScanner` → `ProjectContext`, `SourceFile` (patterns ignorés) | 2 pts | S1 |
| P0 | `LanguageParser`, `ParserRegistry`, `TreeSitterParser` (Template Method) | 3 pts | — |
| P0 | `PythonParser` : symboles, bases, imports, appels (`ParsedModule`) | 5 pts | TreeSitterParser |
| P0 | `CodeStructureExtractor` → `ExtractionResult` avec provenance fichier/ligne | 3 pts | PythonParser |
| P0 | `GraphBuilder` (fusion, dédoublonnage, résolution inter-fichiers) + pipeline | 3 pts | extracteur |

**Charge :** 16 pts
**Risque :** installation de Tree-sitter sous Windows → valider les wheels en début de sprint ; repli possible sur `ast` derrière la même interface `LanguageParser` (à consigner dans ADR-003).

---

## Sprint Plan : S4 — Requêtes et impact
**Objectif :** `dependencies`, `dependents`, `path` et un `ImpactReport` groupé par niveau à partir d'une description textuelle.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `GraphQueryEngine.find/dependencies/dependents/path` | 3 pts | S1 |
| P0 | `TraversalStrategy` + `BoundedBfsStrategy` | 3 pts | S1 |
| P0 | `ChangeRequest`, `ImpactAnalyzer.locate` (lexical) + `analyze` | 3 pts | stratégies |
| P0 | `ImpactReport.by_type` + `to_markdown` | 2 pts | analyzer |
| P1 | Tests sur un graphe issu du reverse de SAKG lui-même | 3 pts | S3 |

**Charge :** 14 pts

---

## Sprint Plan : S5 — Façade, CLI, Mermaid (jalon MVP)
**Objectif :** `sakg init`, `sakg reverse ./src`, `sakg query`, `sakg impact`, `sakg uml --view class` fonctionnent sur le dépôt SAKG.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `ArchitectureService` (méthodes du MVP) | 3 pts | S2–S4 |
| P0 | `ViewProjection` + `MermaidGenerator` (vue CLASS) | 3 pts | S1 |
| P0 | CLI Typer : `init`, `reverse`, `query`, `impact`, `uml` | 3 pts | façade |
| P0 | `.architect/project.yaml` + configuration | 2 pts | init |
| P1 | Dogfooding : reverse de `src/sakg`, diagramme comparé à `docs/uml/class-diagram.md` | 3 pts | tout |
| P1 | ADR-001 à ADR-004 dans `docs/adr/` | 2 pts | — |

**Charge :** 16 pts

---

## Sprint Plan : S6 — Endpoints FastAPI
**Objectif :** le graphe d'un projet FastAPI contient ses routes, reliées au fichier qui les
expose et à la fonction qui les implémente, préfixes de routeurs compris.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `CallSite` : appels au niveau module dans le parser (`APIRouter(prefix=…)`, `include_router`) | 3 pts | S3 |
| P0 | `FrameworkAdapter` + `FastApiAdapter` : routes des décorateurs, préfixes locaux et importés | 5 pts | CallSite |
| P0 | `ApiExtractor` : nœuds `Endpoint`, relations `exposes` et `implemented_by` | 3 pts | adaptateur |
| P0 | Ontologie : `File exposes Endpoint`, `Endpoint implemented_by Function` | 1 pt | — |
| P1 | Dette : `pipeline.warnings` retourné avec le graphe au lieu d'un état d'instance | 2 pts | — |
| P1 | Dette : imports `if TYPE_CHECKING` marqués `type_only` sur la relation | 2 pts | — |

**Charge :** 16 pts
**Risque :** les préfixes de routeurs se résolvent entre fichiers ; se limiter aux cas
observables (`include_router` avec un routeur importé d'un module du projet) et ne rien
inventer quand la chaîne n'est pas traçable.

---

## Sprint Plan : S7 — Données et infrastructure
**Objectif :** le graphe d'un projet contient ses tables et ses conteneurs, reliés au code qui
les définit ; « quelle table ce changement touche-t-il ? » devient une question traitable.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `AttributeRef` : le parser retient les attributs de classe (`__tablename__`, `Column(...)`) | 3 pts | S3 |
| P0 | `DatabaseExtractor` : modèles SQLAlchemy → `Table`, `Column`, `maps_to`, `contains`, `references` | 5 pts | AttributeRef |
| P0 | `InfrastructureExtractor` : `docker-compose` → `Container`, image en `Technology`, dépendances entre conteneurs | 4 pts | — |
| P0 | Ontologie : `Table contains Column`, `File contains Container`, `Container depends_on Container`, `Container uses_technology Technology` | 1 pt | — |
| P1 | Dette : `add_api_route` (route déclarée sans décorateur) | 2 pts | S6 |

**Charge :** 15 pts
**Risque :** une clé étrangère désigne une table par son nom, pas par un chemin ; ne relier que
ce qui existe dans le projet et laisser le reste hors du graphe plutôt que d'inventer une cible.

---

## Sprint Plan : S8 — Diff et historique
**Objectif :** répondre à « qu'est-ce qui a changé dans l'architecture entre ces deux
versions ? » sans relire le code, et rendre l'historique consultable à coût constant.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `ArchitectureDiff` + `GraphDiffer` : ajouts, suppressions, modifications de nœuds et de relations | 5 pts | S2 |
| P0 | `SnapshotMeta` : lister l'historique sans recharger chaque graphe archivé (dette S2) | 3 pts | S2 |
| P0 | `sakg diff v1 v2` et `ArchitectureService.diff` | 3 pts | GraphDiffer |
| P1 | Dette : dépendances au niveau symbole (`from core.base import BaseService`) pour que `dependents` d'une classe réponde | 3 pts | S3 |
| P1 | Ontologie : `File depends_on Class`, `File depends_on Function` | 1 pt | — |

**Charge :** 15 pts
**Risque :** un diff bavard ne sert à rien ; le hash d'ADR-005 définit déjà ce qui compte
comme changement, s'y tenir plutôt que de comparer les fichiers ligne à ligne.

---

## Sprint Plan : S9 — Règles et dérive
**Objectif :** exprimer les règles d'architecture d'un projet en YAML, les vérifier en CI
(`sakg validate` échoue sur une violation), et savoir si le graphe enregistré décrit encore
le code (`sakg drift`). Premier client : SAKG lui-même, dont les règles d'`AGENTS.md`
deviennent des règles vérifiées par l'outil.

| Priorité | Élément | Estimation | Dépendances |
|---|---|---|---|
| P0 | `ArchitectureRule`, `Finding`, `Severity`, `ValidationReport`, `ArchitectureValidator` | 3 pts | S1 |
| P0 | `LayerDependencyRule` : les couches internes ne dépendent pas des couches externes | 3 pts | règles |
| P0 | `NoCycleRule` : cycles d'import d'exécution (les imports `TYPE_CHECKING` n'en créent pas) | 2 pts | règles |
| P0 | `RuleLoader` : `.architect/rules/*.yaml`, registre de types de règles (règle 6) | 2 pts | règles |
| P0 | `sakg validate` (code de sortie ≠ 0 sur erreur, UC08) | 1 pt | façade |
| P1 | `DriftDetector` + `sakg drift` : graphe enregistré ↔ code actuel, distance de Jaccard (ARCHITECTURE §8) | 3 pts | S8 |
| P2 | Dette S8 : impact pondéré (`WeightedPropagationStrategy`) | 3 pts | S4 |

**Charge :** 17 pts (14 sans P2)
**Risque :** une règle qui signale à tort est vite désactivée ; chaque constat doit citer les
nœuds et la relation en cause, pour être vérifiable en une lecture.

---

## Definition of Done (tous sprints)
- [ ] Tests `pytest` verts, nouveaux comportements couverts
- [ ] `ruff check .` et `mypy src` sans erreur
- [ ] Règles d'`AGENTS.md` respectées (provenance, commandes, dépendances du cœur)
- [ ] Noms identiques aux diagrammes UML, ou diagramme mis à jour dans le même commit
- [ ] Revue via `requesting-code-review`
