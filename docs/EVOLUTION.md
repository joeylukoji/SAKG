# Évolution de SAKG

Journal chronologique de ce qui a été **fait**, étape par étape — à la différence de
[`docs/sprints/PLAN.md`](sprints/PLAN.md) (ce qui est prévu) et de `docs/adr/` (pourquoi une
décision structurante a été prise). Une entrée ici répond à « qu'est-ce qui a changé, et
qu'est-ce que ça a coûté à faire marcher ? ».

Ce fichier grandit à chaque étape marquante (fin de sprint, fonctionnalité livrée, écart au
plan). Il ne remplace pas la table « Avancement » de `PLAN.md` : il la détaille quand une étape
mérite plus qu'une ligne.

## Comment ajouter une entrée

En fin d'étape (à la suite de `requesting-code-review` / `code-review`), ajouter une section au
format suivant, la plus récente en haut :

```markdown
## AAAA-MM-JJ — Titre court

**Portée :** sprint concerné ou « hors plan / anticipé sur X » si l'ordre du plan n'a pas été
respecté.

**Ce qui a changé :** liste des composants ajoutés ou modifiés, avec leur fichier.

**Bugs trouvés et corrigés en cours de route :** le cas échéant — c'est souvent la partie la
plus utile à relire plus tard.

**Dette laissée derrière :** ce qui reste à faire, avec un pointeur vers `PLAN.md` si c'est déjà
suivi là-bas.

**État des vérifications :** nombre de tests, `ruff`, `mypy --strict`.
```

Ne pas dupliquer le détail déjà dans un ADR : y renvoyer (`docs/adr/ADR-00X-....md`) plutôt que
recopier la justification d'une décision.

---

## 2026-09-22 — S9 : règles d'architecture et détection de dérive

**Portée :** S9 (« Règles et dérive »), fait dans l'ordre du plan cette fois — contrairement à
l'étape TypeScript/Next.js ci-dessous. P0 et P1 du backlog complets ; P2 (impact pondéré,
`WeightedPropagationStrategy`) reporté, comme le permettait déjà l'estimation du sprint
(« 17 pts, 14 sans P2 »).

**Ce qui a changé :**
- `src/sakg/validation/rules.py` — `ArchitectureRule` (Protocol : `id`, `severity`,
  `check(graph) -> list[Finding]`), `LayerDependencyRule` (une couche interne ne dépend jamais
  d'une couche plus externe ; le module d'un nœud vient de sa propriété `module`, le préfixe de
  couche le plus long l'emporte) et `NoCycleRule` (cycles parmi les relations `depends_on`
  d'exécution, via `networkx.simple_cycles` sur un graphe filtré à la main — un import sous
  `TYPE_CHECKING` ne ferme jamais un cycle).
- `src/sakg/validation/loader.py` — `RuleRegistry` (types de règles enregistrés par nom, règle
  6 d'AGENTS.md), `default_rule_registry()`, `RuleLoader.load(dir)` qui lit
  `.architect/rules/*.yaml` (une entrée = un `type` + sa configuration).
- `src/sakg/validation/validator.py` — `ArchitectureValidator.validate(graph)`, qui agrège les
  constats de toutes les règles enregistrées en un `ValidationReport`.
- `src/sakg/analysis/drift.py` — `DriftDetector.detect(intended, actual) -> DriftReport`
  (`drift_score`, `missing_in_code`, `undocumented_in_code`), distance de Jaccard sur
  l'identité `(source, relation, cible)` des relations (ARCHITECTURE.md §8). Réutilise
  `GraphDiffer.diff_graphs` déjà là depuis S8 plutôt que de recalculer un diff à la main.
- `ArchitectureService.validate()` (UC08) et `.detect_drift()` (UC09) dans
  `src/sakg/application/service.py` ; `sakg validate` et `sakg drift` dans
  `src/sakg/interfaces/cli.py`, tous deux avec un code de sortie ≠ 0 sur violation ou dérive.
  `detect_drift()` ne recalcule que la couche observée d'une **copie** du graphe
  (`ReplaceObservedLayerCommand`, comme `reverse()` le fait déjà pour décider s'il enregistre
  une nouvelle version) : un nœud `USER_DEFINED` ajouté à la main n'est jamais confondu avec
  une dérive.
- `project.yaml`'s `rules: list[str]` (déjà présent, jamais utilisé avant S9) sert de liste
  blanche optionnelle d'identifiants de règles actives ; vide, toutes les règles trouvées
  s'appliquent.
- `.architect/rules/agents-md.yaml` — premier client réel, dogfooding : encode les couches
  d'AGENTS.md (`sakg.domain` → … → `sakg.interfaces`) et l'absence de cycle. `sakg reverse` puis
  `sakg validate` sur SAKG lui-même : **conforme**, 0 % de dérive.

**Décisions prises en écart du diagramme de classes** (`docs/uml/class-diagram.md`), documentées
plutôt que suivies aveuglément :
- `LayerDependencyRule.layers` est une liste **plate** de préfixes (pas de tiers imbriqués) : le
  diagramme le dit ainsi (`List~str~`), et aucun des cinq modules de la couche « métier »
  (`reverse`, `analysis`, `validation`, `generation`, `ai`) n'importe aujourd'hui les autres, donc
  l'ordre choisi entre eux ne change rien en pratique.
- `NoCycleRule ..> MetricsCalculator` (le diagramme fait dépendre la règle du futur calculateur
  de métriques) n'a pas été suivi : `MetricsCalculator` n'est dans le backlog d'aucun sprint
  planifié, et bâtir une coquille à trois méthodes non implémentées juste pour cette dépendance
  aurait coûté plus qu'il n'aurait apporté. `NoCycleRule` détecte donc ses cycles elle-même ; à
  reprendre si `MetricsCalculator` voit le jour (noté dans `PLAN.md`, non planifié).
- Le champ `Finding.edge_ids` manquait au diagramme alors qu'il existe déjà dans
  `validation/findings.py` et qu'il est requis par le risque même du sprint (« chaque constat
  doit citer les nœuds et la relation en cause ») : ajouté au diagramme plutôt qu'à l'inverse.

**Dette laissée derrière** (détail dans `PLAN.md`) : impact pondéré (P2, reporté une seconde
fois), `sakg drift` non câblé dans un workflow CI, mots vides et seuils de correspondance
toujours figés dans le code, `TraceabilityRule`/`OrphanComponentRule` du diagramme non
implémentées, `NoCycleRule` à reprendre si `MetricsCalculator` est un jour construit.

**État des vérifications :** 376 tests (46 nouveaux : règles, chargeur, validateur, dérive,
service, CLI), `ruff check .` et `mypy --strict` verts. Dogfooding réel, pas seulement des
tests unitaires : `sakg reverse` (v11, 546 nœuds, 1 323 relations) puis `sakg validate` et
`sakg drift` exécutés pour de vrai sur ce dépôt.

---

## 2026-09-22 — TypeScript (structure) et Next.js (App Router), anticipés avant S9

**Portée :** hors plan. `docs/sprints/PLAN.md` classait ce travail en phase 7 (S13+, après
Règles/Dérive S9, IA S10–S11 et MCP S12) ; il a été fait maintenant à la place, sur demande
explicite plutôt qu'en suivant l'ordre des sprints.

**Ce qui a changé :**
- `src/sakg/reverse/languages.py` — table des langages reconnus par suffixe (`.ts`, `.tsx`,
  `.js`, `.dart`, `.java`, `.kt`, `.cs`, `.php`, `.go`, `.rb`…), `detection_tag` pour préfixer
  la provenance par langage (`TYPESCRIPT_...`, en gardant `PYTHON_AST_...` pour ADR-005), et
  `module_name_of` pour dériver un nom de module pointé du chemin de fichier.
- `src/sakg/reverse/tree_sitter_parser.py` — `TreeSitterParser`, squelette Template Method
  prévu par ADR-003 : un langage = une grammaire + une collecte vers `ParsedModule` ; lecture
  du fichier, construction du parseur Tree-sitter et erreurs d'I/O mutualisées.
- `src/sakg/reverse/typescript_parser.py` — `TypeScriptParser` : classes, méthodes, fonctions,
  imports ESM (`import { X } from "./y"`), appels, héritage (`extends`). `.tsx` utilise la
  grammaire TSX, le reste du pipeline ne voit qu'un langage `typescript`.
- `src/sakg/reverse/imports.py` — `EcmaImportResolver`, pour résoudre `from "./base"` et
  `from "../core"` en nom de module du projet ; `PythonImportResolver` inchangé.
- `src/sakg/reverse/adapters.py` — `NextJsAdapter`, nouveau `FrameworkAdapter` enregistré dans
  `ApiExtractor` à côté de `FastApiAdapter`. Différence de nature avec FastAPI : pas de
  décorateur à reconnaître, le verbe HTTP vient du nom d'une fonction exportée au premier
  niveau (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`) dans un fichier
  `app/**/route.ts`, et le chemin vient de l'arborescence des dossiers :
  - `[id]` → `{id}` (segment dynamique)
  - `[...slug]` → `{...slug}` (tout-venant)
  - `[[...slug]]` → `{...slug?}` (tout-venant optionnel)
  - `(marketing)` → ignoré dans l'URL (groupe de routage)
  - `_lib/...` → aucune route (dossier privé, comme dans Next.js)
  `routers()` et `inclusions()` ne retournent jamais rien : il n'y a rien à monter entre
  fichiers, contrairement aux routeurs FastAPI.
- Un langage sans parser (JavaScript, Dart, Java…) devient un nœud `File` d'inventaire, avec
  **un** avertissement par langage plutôt qu'un par fichier.
- `sakg reverse` lit désormais `languages` dans `.architect/project.yaml` (SAKG lui-même reste
  configuré en `python` seul, donc son propre graphe dogfoodé n'en tient pas compte).

**Bugs trouvés et corrigés en cours de route :**
- `TypeScriptParser._bases()` ne dépliait pas le nœud `extends_clause` que Tree-sitter place
  sous `class_heritage` : `class X extends Y` ne produisait **aucune** relation `INHERITS`.
  Symptôme découvert en faisant échouer `tests/reverse/test_typescript.py` avant de le corriger
  (le code livré ne passait pas encore les tests ajoutés avec lui).
- `ApiExtractor._add_endpoints` écrivait en dur `PYTHON_AST_ROUTE_DECLARATION` et
  `PYTHON_AST_ROUTE_HANDLER` dans la provenance des relations `exposes` / `implemented_by`,
  quel que soit le langage réel du fichier. Un endpoint Next.js aurait donc menti sur sa
  méthode de détection. Remplacé par `detection_tag(module.file.language, ...)`, comme le fait
  déjà `CodeStructureExtractor`.
- `tests/analysis/test_impact.py::test_a_fragmented_word_does_not_impact_the_whole_graph`
  démontrait qu'un mot composé (« TypeScript » → fragments `type` + `script`) ne devait
  produire qu'une correspondance faible dans le graphe de SAKG lui-même. Le nouveau code rend
  ce test faux par sa seule existence : SAKG contient maintenant un vrai `TypeScriptParser`,
  donc « TypeScript » y correspond fortement — ce qui est le comportement *correct* de
  l'analyse d'impact, pas une régression. Remplacé l'exemple par « GraphType » (fragments
  `graph` + `type`, toujours sans correspondance forte), en documentant pourquoi dans le test.

**Dette laissée derrière** (détail dans `PLAN.md`, section Dette, cible S13+) : pas de parser
JavaScript (`.js`/`.jsx` restent de l'inventaire pur), pas de `DjangoAdapter` ni
`ExpressAdapter`, pages Next.js (`page.tsx`) volontairement hors `ApiExtractor` (c'est du
routage UI, pas un endpoint HTTP — pas de verbe, pas de handler au sens de l'ontologie
actuelle), aucun parser pour Go/Dart/Java/Kotlin/C#/PHP/Ruby au-delà de l'inventaire de
fichiers.

**État des vérifications :** 340 tests (dont 4 nouveaux pour l'héritage/imports TypeScript déjà
présents avant cette étape, et 15 nouveaux pour `NextJsAdapter`), `ruff check .` et
`mypy --strict` verts. Vérifié en bout en bout avec un mini-projet Next.js jetable passé dans
`ReverseEngineeringPipeline.default().run_on(...)`, pas seulement via les tests unitaires.
