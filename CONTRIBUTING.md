# Contribuer à SAKG

Merci de votre intérêt ! SAKG est un projet open source sous licence [MIT](LICENSE).

## Prendre une tâche

### Règle : une proposition approuvée avant de coder

Pour que deux personnes ne travaillent jamais sur la même partie, **aucun travail ne commence
sans l'accord du mainteneur** ([@joeylukoji](https://github.com/joeylukoji)) :

1. **Choisir une tâche** dans [Tâches ouvertes](README.md#tâches-ouvertes) et vérifier qu'aucune
   PR ouverte ne la cite déjà (onglet *Pull requests*, recherche `Txx`).
2. **Ouvrir une PR de proposition**, en brouillon (*draft*), sur une branche
   `txx-description-courte` créée depuis `main`. Titre : `[Proposition] Txx — <titre>`.
   Elle ne contient pas encore de code : sa description explique ce que vous voulez faire,
   les fichiers et modules touchés, l'approche envisagée et une estimation.
3. **Attendre l'approbation.** Le mainteneur répond dans la PR : approuvée (la tâche vous est
   attribuée), à revoir, ou refusée. **Ne commencez à coder qu'après l'approbation.**
4. **Coder dans cette même PR**, puis la passer en « Ready for review » quand la
   [Definition of Done](#definition-of-done) est remplie.

Une tâche attribuée sans activité pendant deux semaines peut être réattribuée.
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
