# ADR-005 — Ce que le hash du graphe prend en compte

- **Statut :** accepté
- **Date :** 2026-09-17
- **Concerne :** `src/sakg/graph/snapshot.py`, sprints S2 et S8

## Contexte

`GraphSnapshot.graph_hash` identifie l'état du graphe. Son périmètre détermine ce que
« l'architecture a changé » veut dire, et conditionne le diff (S8) comme la détection de
dérive (S9).

## Décision

Le hash porte sur : identifiant, type, nom et `properties` de chaque nœud ; identifiant,
extrémités, relation et `properties` de chaque relation ; et, pour la provenance, uniquement
`evidence_type` et `confidence`.

Sont exclus : `created_at`, `graph_version`, `commit_sha`, `detected_by` et `evidence`
(fichier et ligne).

## Justification

- Deux reverse successifs d'un code inchangé doivent donner le même hash, sinon chaque
  exécution ressemblerait à un changement d'architecture et le diff serait inutilisable.
- `confidence` et `evidence_type` sont inclus : passer une relation d'INFERRED à OBSERVED est
  un vrai changement de ce que l'on sait de l'architecture.
- `evidence` est exclu : déplacer une classe de dix lignes dans son fichier ne change pas
  l'architecture. La contrepartie est qu'un tel déplacement est invisible au hash, alors que
  les fichiers de `.architect/` changent — le `git diff` reste la source de détail.

## Conséquences

- Les `properties` des nœuds et relations doivent rester sérialisables en JSON ; c'est
  documenté sur `Node` et `Edge`.
- Le futur `DriftDetector` (S9) compare des ensembles de relations, pas des hashes : ces deux
  mécanismes sont complémentaires.
