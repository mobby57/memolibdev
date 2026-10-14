# Plan directeur stratégique — MemoLibDev

> **Statut : vision directrice à long terme.** Ce document fixe le cap produit. Les étapes et priorités opérationnelles peuvent évoluer selon les audits, les preuves, les retours utilisateurs et les résultats commerciaux, sans perdre cette vision.

## 1. Vision à long terme — cap à préserver

**MemoLibDev a vocation à devenir une plateforme universelle capable de comprendre les besoins de chaque métier, de guider l’utilisateur et de piloter des agents IA pour créer, adapter et vérifier des solutions, des applications et des documents professionnels : actes juridiques, contrats, rapports, procédures et autres livrables métier.**

La plateforme doit pouvoir s’adapter à des secteurs, des pays, des langues, des organisations et des niveaux techniques différents, sans enfermer son moteur central dans un seul métier.

Cette universalité est une **ambition à construire progressivement**, et non une capacité déjà considérée comme acquise.

## 2. Stratégie produit

Construire dans cet ordre :

1. **Socle fiable : agent IA contrôlé.** Comprendre une mission, analyser le contexte réel du projet, proposer une action, produire des preuves, vérifier les résultats et respecter strictement les autorisations humaines.
2. **Guide de développement assisté par IA (« vibe coding »).** Aider les débutants comme les développeurs à clarifier leur besoin, le découper en étapes, choisir les actions appropriées, interpréter les erreurs et avancer avec des résultats vérifiables.
3. **Packs métier.** Ajouter progressivement des connaissances, modèles, règles, workflows et contrôles propres à chaque profession, juridiction ou secteur, tout en conservant un moteur commun.
4. **Production de livrables professionnels.** Permettre de générer et d’adapter des documents, actes, contrats, rapports, procédures et autres contenus métier, avec sources ou éléments de preuve lorsque cela est pertinent et validation humaine lorsque nécessaire.
5. **Plateforme universelle extensible.** Étendre l’adaptation aux différents métiers, pays, langues, outils et environnements selon les besoins confirmés du marché.

## 3. Principes non négociables

- **Contrôle humain :** aucune action sensible, application de changement ou décision métier engageante sans autorisation explicite adaptée.
- **Preuves et traçabilité :** distinguer clairement ce qui a été demandé, analysé, proposé, exécuté et réellement vérifié.
- **Sécurité par défaut :** périmètre explicite, isolation, refus en cas de doute, permissions minimales et absence de contournement des contrôles.
- **Honnêteté sur les capacités :** ne jamais présenter une proposition comme une action réalisée ni un test non exécuté comme réussi.
- **Réversibilité :** protéger le travail existant, prévoir les moyens de contrôler et de revenir sur les changements lorsque cela est possible.
- **Moteur générique, extensions spécialisées :** ne pas coder toute la logique dans un seul métier ou pays ; utiliser des packs configurables.
- **Progression fondée sur les preuves :** préserver les acquis et les tests ; auditer avant de modifier ; valider chaque étape avant d’élargir le périmètre.
- **Internationalisation pragmatique :** commencer avec les besoins et langues les mieux validés, puis étendre selon la demande réelle.

## 4. Feuille de route

### Phase A — Audit et état de référence
- Établir l’état réel du dépôt, de l’architecture, des protections, des tests et des fonctions déjà opérationnelles.
- Distinguer les capacités démontrées, les capacités partielles et les objectifs encore théoriques.
- Préserver les travaux existants et établir une référence mesurable.

### Phase B — Fiabiliser le moteur contrôlé
- Consolider la compréhension du projet et de la mission, la planification, la provenance des informations, les preuves et l’approbation humaine.
- Maintenir le passage obligatoire par les mécanismes contrôlés ; aucune voie parallèle ne doit contourner les garde-fous.
- Renforcer l’exécution isolée, la vérification, la gestion des échecs, la traçabilité et le retour arrière.
- Mesurer les réussites, la pertinence des propositions, les erreurs, les délais et les éventuels contournements.

### Phase C — Guider l’utilisateur de bout en bout
- Transformer un objectif parfois imprécis en étapes compréhensibles et validables.
- Expliquer les choix, risques, prérequis, erreurs et résultats dans un langage accessible.
- Prévoir une expérience simple pour les débutants et une vue détaillée pour les développeurs.
- Garder l’utilisateur maître des décisions et des autorisations.

### Phase D — Valider la valeur métier et commerciale
- Tester des cas réels, d’abord dans un périmètre limité et maîtrisé.
- Rechercher des utilisateurs externes pilotes et mesurer le temps gagné, la fiabilité et la fréquence d’usage.
- Vérifier la volonté de payer avant de considérer les prix ou le modèle économique comme validés.
- Élargir le produit uniquement lorsque les preuves d’utilité, de sécurité et de demande sont suffisantes.

### Phase E — Ajouter les packs métier et les documents
- Choisir les premiers métiers à partir de besoins observés, et non d’hypothèses seules.
- Créer des modèles, règles, workflows et contrôles adaptés à chaque contexte.
- Pour les domaines réglementés ou à fort enjeu, séparer la collecte des faits, l’analyse, la proposition et la validation par une personne compétente.
- Conserver un noyau générique et permettre d’ajouter ou de faire évoluer les packs sans casser les usages existants.

### Phase F — Étendre progressivement à l’international
- Commencer par les langues et marchés validés.
- Prévoir la localisation, les formats, les règles et les exigences propres à chaque pays ou secteur.
- Tester chaque extension avant de la déclarer prête.
- Construire l’ambition universelle par extensions vérifiées et réutilisables, pas par une promesse de compatibilité immédiate avec tous les métiers.

## 5. Discipline d’exécution

- Commencer par une lecture et un audit en mode lecture seule.
- Ne pas modifier, appliquer, tester avec des modèles locaux, committer ou pousser sans autorisation explicite correspondant à l’action.
- Ne pas supprimer ni refondre les composants existants sans justification et validation.
- Pour chaque changement autorisé : annoncer le périmètre, préserver la référence, recueillir des preuves et rapporter précisément ce qui a été fait et vérifié.
- Traiter la sécurité, la qualité et la confiance comme des fonctionnalités centrales, pas comme des ajouts ultérieurs.

## 6. Critère de réussite à long terme

MemoLibDev réussira si des personnes de métiers et de niveaux techniques différents peuvent décrire un besoin, être guidées vers une solution adaptée, produire des livrables utiles et vérifier les résultats avec moins d’effort et davantage de contrôle — sans sacrifier la sécurité, la traçabilité ni le jugement humain.

**Règle directrice :** avancer par preuves, commencer par un agent contrôlé fiable, ajouter les capacités métier progressivement et garder comme horizon une plateforme universelle d’assistance, de création et de vérification.
