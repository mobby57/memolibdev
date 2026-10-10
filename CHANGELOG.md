\# Changelog

## [V3.5.4-L] - 2026-10-10

### Ajouté
- Preuve du rollback automatique : apply -> verify fail -> rollback -> SHA identique
- Test `test_rollback_strict3.py` forcant un echec de verification
- Documentation du comportement fail-closed en cas d'echec POST_VERIFY

### Résultat
- `STATUT : ROLLED_BACK`, `rolled_back=True`, `apply_status=ROLLED_BACK`
- SHA final identique au SHA initial : `cc118a2e...`
- Le fichier est preserve en cas d'echec de verification

### Signification
- Le systeme peut modifier ET annuler proprement.
- Contrairement a Cursor/Kiro/Copilot, MemoLibDev garantit la restauration apres echec.

## [V3.5.4-K] - 2026-10-10

### Ajouté
- Mode `SUPERVISED_APPLY` fonctionnel : modification reelle de fichier apres approbation humaine
- Chaine d'autorisation complete : proposition -> approbateur -> confirmation -> apply
- Fail-closed verifie : refus d'agir sans intent disponible

### Résultat
- Fichier `sample.py` modifie avec succes (renommage `hello` -> `greet`)
- `STATUT : APPLIED` avec `POST_VERIFY PASS`
- Le fichier est restaure a son etat initial en cas d'echec de verification

## [V3.5.4-J] - 2026-10-10

### Ajouté
- Mode PROPOSE : genere un diff de code a partir d'une mission en langage naturel
- Appel LLM local (Ollama) pour produire un LLMPlan (REPLACE:old:new)
- Affichage enrichi (resume, fichiers, SHA avant, diff complet)
- Support de plusieurs modeles Ollama

### Modifié
- OllamaProvider.http_timeout : 60 -> 300 s
- OllamaProvider.num_predict : 64 -> 256
- Prompt Ollama : exemples explicites, regles strictes

### Bugs corriges
- Format REPLACE : rejet des '::' parasites (validation stricte)
- Exemple du prompt : ':' final retire
- Reponse vide Ollama : causee par num_predict=64 trop bas

## [V3.5.4-I] - 2026-10-10

### Ajouté
- Synthese descriptive derivee des faits observes
- 4 nouvelles categories de detection : DEFINITION, DOC_HEADING, DOC_LIST, DOC_TABLE
- Enrichissement de _DOMAIN_RELEVANT_CATEGORIES pour le domaine DOC
- Enrichissement de _BEHAVIORAL_CATEGORIES avec DEFINITION et DOC_HEADING

### Amélioré
- Extraction de faits : 1 -> 9 sur un depot de test simple
- Confiance d'analyse : LOW -> MEDIUM

### Résultat
- 61 PASS / 0 FAIL sur test_analysis_builder.py

## [V3.5.4-H] - 2026-10-10

### Ajouté
- Interface web complete (champ `project` ajoute)
- Messages humanises corriges (ANALYZED, AWAITING_AUTHORIZATION, REFUSED)

## [V3.5.4-G] - 2026-10-10

### Ajouté
- Infrastructure de campagne formelle (worker + superviseur isole)
- Manifeste runtime : modules charges avec SHA-256
- Trace chainee (hash de l'evenement precedent)
- Assertions honnetes : PASS / FAIL / INCONCLUSIVE

### Résultat
6 assertions PASS, 1 INCONCLUSIVE (honnete et justifiee)

## [V3.5.4-F] - 2026-10-10

### Ajouté
- Campagne initiale de validation





\## \[V3.5.4-H] - 2026-10-10



\### Ajouté

\- Campagne V3.5.4-G : infrastructure de preuve complète

\- Worker + superviseur isolés en sous-processus

\- Trace chaînée (hash de l'événement précédent)

\- Manifeste runtime avec SHA-256 des modules

\- Assertions honnêtes : PASS / FAIL / INCONCLUSIVE

\- 4 nouvelles catégories de détection : DEFINITION, DOC\_HEADING, DOC\_LIST, DOC\_TABLE

\- Enrichissement de \_DOMAIN\_RELEVANT\_CATEGORIES pour le domaine DOC

\- Enrichissement de \_BEHAVIORAL\_CATEGORIES avec DEFINITION et DOC\_HEADING



\### Amélioré

\- Extraction de faits : 1 → 9 sur un dépôt de test simple

\- Confiance d'analyse : LOW → MEDIUM

\- Pertinence du diagnostic sur documentation et code Python



\### Résultat V3.5.4-G

6 assertions PASS, 1 INCONCLUSIVE (honnête et justifiée)



\### Inchangé

\- Aucune modification d'écriture en mode READ\_ONLY

\- Honnêteté du rapport maintenue



\### Limites connues

\- Pas de synthèse descriptive automatique (à venir V3.5.4-I)

\- Mode APPLY non testé de bout en bout avec rollback

\- Preuve locale uniquement (pas de CI isolée)

