# ADR-002 — Graphe en mémoire avec structures propres, NetworkX en complément

- **Statut :** accepté
- **Date :** 2026-09-17
- **Concerne :** `src/sakg/graph/`, sprints S1 et S4

## Contexte

`docs/ARCHITECTURE.md` prévoit NetworkX pour les traversées. Restait à décider si
`KnowledgeGraph` *est* un graphe NetworkX ou s'il en expose seulement une conversion.

## Décision

`KnowledgeGraph` conserve ses propres index (`dict` de nœuds et de relations, listes
d'adjacence). `to_networkx()` produit un `MultiDiGraph` à la demande.

Les traversées du MVP (`BoundedBfsStrategy`, `GraphQueryEngine.path`) sont écrites
directement sur ces index.

## Justification

- Le graphe porte des invariants propres à SAKG : unicité des identifiants, validation par
  l'ontologie, provenance obligatoire. Les faire respecter à travers l'API de NetworkX
  demanderait une couche d'adaptation de toute façon.
- Plusieurs relations peuvent relier la même paire de nœuds, d'où `MultiDiGraph` et non
  `DiGraph` lors de la conversion.
- NetworkX reste disponible pour ce qu'il fait bien et que nous ne réécrirons pas :
  détection de cycles, composantes, centralité, plus court chemin pondéré (sprints S8 et S9).

## Conséquences

- Le cœur ne dépend de NetworkX que pour `to_networkx()` ; la règle 1 d'`AGENTS.md` l'autorise.
- Une bascule vers une base graphe (Neo4j) resterait possible derrière `GraphRepository`.
- Les algorithmes avancés devront passer par la conversion, dont le coût est à mesurer sur de
  gros graphes avant de l'appeler en boucle.
