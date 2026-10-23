# Contribuer à SAKG

Merci de votre intérêt ! SAKG est un projet open source sous licence [MIT](LICENSE).

## Prendre une tâche

1. Choisir une tâche dans la section **[Tâches ouvertes](README.md#tâches-ouvertes)** du README
   (chaque tâche a un identifiant `Txx`, un module, une difficulté et ses dépendances).
2. Ouvrir une issue `Txx — <titre>` (ou commenter l'issue existante) pour signaler que vous la
   prenez : cela évite que deux personnes travaillent sur la même chose.
3. Créer une branche `txx-description-courte` depuis `main`.
4. Ouvrir une pull request qui cite la tâche ; le modèle de PR rappelle la liste de vérifications.

Les tâches marquées 🟢 sont de bonnes premières contributions.

## Environnement

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check . && mypy src
```

La CI (GitHub Actions) exécute ces trois commandes sur Python 3.11 et 3.13 pour chaque PR.

## Avant d'écrire du code

Lire, dans cet ordre :

- [`AGENTS.md`](AGENTS.md) — règles d'architecture **non négociables** et conventions ;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — couches, modules, patterns, flux ;
- [`docs/uml/class-diagram.md`](docs/uml/class-diagram.md) — classes cibles ;
- [`docs/sprints/PLAN.md`](docs/sprints/PLAN.md) — contexte des tâches et dette connue.

En résumé :

- `src/sakg/domain` et `src/sakg/graph` n'importent que la bibliothèque standard, Pydantic et
  NetworkX (vérifié par `tests/architecture/`).
- Toute création de `Node` ou `Edge` fournit une `Provenance` complète ; toute modification du
  graphe passe par une `GraphCommand` exécutée par le `CommandBus`.
- Un nouveau langage, framework, règle ou fournisseur LLM = une nouvelle classe enregistrée dans
  un registre, sans modifier le cœur.
- Mieux vaut **ne rien produire qu'un fait faux** : ce qui n'est pas traçable devient un
  avertissement, pas une relation inventée.

## Definition of Done

- Tests `pytest` verts, nouveaux comportements couverts ;
- `ruff check .` et `mypy --strict` sans erreur ;
- noms identiques aux diagrammes UML, ou diagramme mis à jour dans la même PR ;
- une décision structurante = une ADR dans `docs/adr/` ;
- une entrée dans [`docs/EVOLUTION.md`](docs/EVOLUTION.md) pour toute étape marquante ;
- la ligne de la tâche retirée (ou cochée) dans le README.

## Langue

La documentation et les messages de commit sont en français ; les identifiants du code suivent
les diagrammes UML (anglais).
