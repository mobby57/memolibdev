# Architecture de MemoLibDev v3

## Flux

Mission utilisateur -> mission_intent -> context_builder -> analysis_builder
-> reponse read-only (mode ANALYSER)

ou

-> agent_loop -> controlled_coder -> sandbox -> coder_authorization
-> approbation humaine -> D5.9 (mode CORRIGER)

## Modules

| Fichier | Role |
|---|---|
| mission_intent.py | Classification (objectif, domaine, type) |
| context/context_builder.py | Selection des fichiers pertinents |
| analysis_builder.py | Extraction de faits sources (SHA + ligne) |
| agent_loop.py | Orchestrateur 10 etapes |
| controlled_coder.py | Generation de patch |
| coder_authorization.py | Binding cryptographique + TTL |
| project_target.py | Resolution de la cible |

## Invariants

- Jamais de sys.exit() au module-level
- Jamais d'ecriture hors sandbox
- Jamais de commit/push automatique
- Jamais d'action sans approbation humaine
- Fail-closed par defaut
- Chaque fait est source (SHA + ligne)