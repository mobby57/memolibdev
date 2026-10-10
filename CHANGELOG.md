\# Changelog



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

