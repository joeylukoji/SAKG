# ADR-004 — L'IA écrit dans le graphe uniquement par propositions

- **Statut :** accepté (mise en œuvre au sprint S10)
- **Date :** 2026-09-17
- **Concerne :** `src/sakg/ai/`, `src/sakg/application/`

## Contexte

SAKG se veut une **source de vérité** architecturale. Un modèle de langage produit des
sorties plausibles mais non vérifiées ; s'il écrivait directement dans le graphe, la
distinction entre ce qui est observé dans le code et ce qui est supposé disparaîtrait.

## Décision

`AIArchitect` n'obtient que des outils de **lecture** (`GraphToolkit`). Il produit des
`ArchitectureProposal` au statut `PROPOSED`, validées contre l'ontologie par
`ProposalValidator` avant d'être présentées. Seule une acceptation humaine déclenche un
`ApplyProposalCommand`, qui passe comme toute mutation par le `CommandBus`.

Les nœuds issus d'une proposition portent une provenance `GENERATED` (confiance 0.3–0.8) ou
`RECOMMENDED`, jamais `OBSERVED`.

## Conséquences

- Le serveur MCP expose d'abord des outils en lecture ; `propose_change` viendra ensuite, et
  aucun outil d'écriture directe ne sera exposé.
- Toute information du graphe reste traçable : on peut toujours répondre à « d'où vient cette
  relation, et qui l'a validée ? ».
- Le coût est un aller-retour humain supplémentaire, assumé : c'est le principe
  « l'IA propose, l'humain dispose » de `docs/ARCHITECTURE.md` §6.
