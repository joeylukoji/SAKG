# ADR-001 — Persistance JSON dans `.architect/`, PostgreSQL plus tard

- **Statut :** accepté
- **Date :** 2026-09-17
- **Concerne :** `src/sakg/infrastructure/`, sprint S2

## Contexte

Le graphe doit être stocké quelque part. Deux propriétés comptent pour SAKG : l'architecture
doit **voyager avec le code** (donc être versionnée dans Git aux côtés des sources), et les
agents IA doivent pouvoir la lire **sans service à démarrer**.

## Décision

Le MVP écrit `nodes.json`, `edges.json` et `meta.json` dans `.architect/graph/`, et archive
chaque version dans `.architect/versions/vNNNN/`. Les listes sont triées par identifiant et
le JSON est indenté, pour que `git diff` reste lisible.

L'accès passe par le port `GraphRepository` : `PostgresGraphRepository` pourra être ajouté
sans toucher au cœur (schéma prévu dans `docs/ARCHITECTURE.md` §7).

## Écriture

Les trois fichiers d'un snapshot sont écrits à côté puis renommés (`os.replace`), et
`meta.json` en dernier : une écriture interrompue laisse l'état précédent intact. À la
lecture, les compteurs de `meta.json` sont confrontés au contenu, et un écart est refusé
plutôt que chargé en silence.

Pour que le `git diff` soit lisible, un reverse **conserve la provenance** d'un nœud ou d'une
relation dont le contenu (au sens d'[ADR-005](ADR-005-perimetre-du-hash.md)) n'a pas changé :
la date et le commit indiquent depuis quand le fait est observé, et non la dernière
exécution. Deux reverse successifs sur un code inchangé produisent des fichiers identiques au
bit près, et aucune nouvelle version n'est enregistrée.

## Conséquences

- Un `git diff` montre ce qui a changé dans l'architecture, relation par relation.
- En auto-analyse, le `commit_sha` enregistré est celui du commit **précédent** : le graphe
  est écrit avant d'être commité. C'est inhérent au dogfooding et sans conséquence pour un
  projet analysé de l'extérieur.
- Aucun service externe à installer pour utiliser SAKG.
- Chaque écriture réécrit le graphe entier : acceptable tant qu'une commande correspond à un
  reverse complet, à revoir si des mutations unitaires deviennent fréquentes (dette S5).
- Pas de requêtes concurrentes ni de transactions : un seul utilisateur à la fois par projet.
