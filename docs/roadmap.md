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


## 7. Positionnement commercial — guider et contrôler le vibe coding

### Positionnement recommandé

MemoLibDev ne doit pas chercher à devenir un simple générateur de code de plus. Son positionnement initial est celui d’un **système de guidage, de vérification et de contrôle pour les personnes qui construisent des logiciels avec l’IA**.

**Promesse de travail :** aider les créateurs de logiciels utilisant l’IA à passer de demandes parfois imprécises à des modifications adaptées au projet, contrôlées et vérifiables.

Le produit doit compléter les assistants de programmation existants, plutôt que chercher immédiatement à les remplacer. La différenciation doit être démontrée par des usages réels ; elle ne doit pas être présumée.

### Les trois orientations, dans l’ordre recommandé

- **Première version commerciale : B — contrôleur des agents IA.** L’utilisateur conserve ses outils habituels ; MemoLibDev aide à encadrer les missions, examiner les propositions, contrôler les autorisations et vérifier les résultats.
- **Évolution suivante : A — guide universel du vibe coding.** Aider les personnes, y compris les débutants, à clarifier leur besoin, à le découper en étapes et à comprendre la prochaine action utile.
- **Vision étendue : C — plateforme complète de développement assisté.** Comprendre le projet, organiser le travail, piloter des agents compatibles et vérifier les résultats de bout en bout.

Cet ordre est un choix stratégique à tester, pas une garantie de réussite commerciale.

### Les quatre capacités centrales

1. **Comprendre avant d’agir :** analyser l’architecture, les fichiers pertinents, les dépendances, les tests et les contraintes disponibles ; demander des précisions lorsque le contexte est insuffisant.
2. **Transformer l’intention en mission :** définir l’objectif, le périmètre, les étapes, les risques, les permissions et les critères de réussite.
3. **Guider et vérifier pendant le travail :** organiser la boucle Comprendre → Planifier → Exécuter → Vérifier → Corriger → Valider, en ne présentant que des résultats appuyés par des preuves.
4. **Contrôler les actions :** conserver les niveaux Observer, Préparer, Tester en environnement isolé et Modifier après autorisation explicite adaptée au périmètre.

### Expérience utilisateur à construire

Prévoir deux modes cohérents sur un même moteur :

- **Mode Développeur :** diagnostics détaillés, diff, tests, risques, provenance et résultats techniques.
- **Mode Créateur assisté par IA :** explications simples, étapes courtes, risques formulés clairement et actions suivantes compréhensibles.

Présenter séparément l’état de compréhension, l’état des preuves et l’état des autorisations. Éviter un score unique de confiance s’il n’est pas fondé sur une mesure validée.

### Architecture cible à long terme

1. **Interfaces :** commencer par une interface principale et n’ajouter le bureau, le web, l’éditeur ou la CLI que si l’usage le justifie.
2. **Compréhension du projet :** adapter l’analyse aux langages, frameworks, configurations et tests rencontrés, sans supposer une pile technique unique.
3. **Moteur de missions :** structurer objectifs, contexte, périmètre, étapes, critères, risques, permissions et preuves attendues.
4. **Connecteurs d’agents et de modèles :** permettre progressivement plusieurs outils et fournisseurs, locaux ou distants, avec une transparence explicite sur les flux de données.
5. **Preuves et contrôles :** tracer les fichiers examinés, propositions, tests réellement exécutés, résultats, approbations et refus ; distinguer validation humaine et preuve technique.

## 8. Public prioritaire et modèle économique à tester

### Segment initial recommandé

Tester d’abord auprès des **entrepreneurs qui construisent leur SaaS avec l’IA et commencent à rencontrer des problèmes de fiabilité** : régressions, corrections difficiles, incertitude sur la sécurité ou difficulté à transformer un prototype en application maintenable.

Ce segment est une hypothèse prioritaire, à confronter à des entretiens et à des essais réels. Les développeurs indépendants et les petites agences constituent des segments alternatifs à évaluer.

### Hypothèses de prix, non validées

Les prix ci-dessous ne sont que des hypothèses de test, pas des tarifs décidés ni une preuve de demande :

- Free : analyse et missions limitées.
- Creator : 19 €/mois.
- Pro : 49 €/mois.
- Team : 149 €/mois.

Avant de fixer les offres, mesurer les coûts réels de calcul, d’hébergement, de support et d’intégration, puis tester la volonté de payer. Le chiffre d’affaires théorique ne doit pas être confondu avec le bénéfice.

## 9. Validation sur 90 jours

### Jours 1–30 : mesurer le moteur sur des missions réelles
- Utiliser MemoLib comme cas d’usage contrôlé, sans compromettre le dépôt ni la production.
- Étudier des missions représentatives : diagnostic de bug, proposition de correction, détection de régression, vérification et refus d’action non autorisée.
- Mesurer la pertinence, le temps, les propositions exploitables, les tests réellement exécutés, les erreurs introduites et les interventions humaines.
- Conserver les échecs dans le bilan ; ne pas sélectionner uniquement les résultats favorables.

### Jours 31–60 : tester avec 5 à 10 personnes externes
- Recruter des personnes qui utilisent déjà l’IA pour créer des applications.
- Les faire essayer le produit sur leurs projets, avec des environnements isolés lorsque nécessaire.
- Observer les usages effectifs, les difficultés, le retour spontané et les demandes répétées.
- Rechercher des preuves d’usage récurrent, pas uniquement des avis positifs.

### Jours 61–90 : tester une première offre
- Si les étapes précédentes sont encourageantes, préparer une démonstration courte, une présentation en français et en anglais, une installation simple et une offre limitée.
- Mesurer l’activation, le retour des utilisateurs, la conversion payante, les coûts et la charge de support.
- À la fin, décider sur la base des résultats : poursuivre, repositionner ou réduire le périmètre.

## 10. Différenciation à démontrer

Les axes à tester sont :

- Indépendance progressive vis-à-vis d’un fournisseur d’IA.
- Prise en compte du contexte réel et des contraintes du projet.
- Résultats et vérifications fondés sur des preuves observables.
- Contrôle explicite des permissions et des modifications.
- Expérience compréhensible par des utilisateurs qui ne maîtrisent pas tous les détails techniques.

Les assistants de programmation évoluent rapidement. Aucun avantage concurrentiel durable ne doit être considéré comme acquis sans comparaison régulière avec les solutions existantes et retour d’utilisateurs.

## 11. Internationalisation

- Préparer l’architecture pour séparer la langue de l’interface de la logique technique.
- Prioriser le français et l’anglais, puis choisir d’autres langues en fonction de la demande observée.
- Ajouter les langages, systèmes, frameworks et connecteurs par étapes, en testant chaque extension.
- Permettre des modes locaux ou distants lorsque cela est réalisable, expliquer quelles données quittent l’environnement de l’utilisateur et offrir des options de confidentialité adaptées.
- Ne pas prétendre être compatible avec tous les outils ou tous les pays avant de l’avoir démontré.

## 12. Synergie entre MemoLibDev et MemoLib

MemoLib peut servir de premier cas d’usage réel pour mesurer la capacité de MemoLibDev à comprendre un dépôt, préparer une proposition, recueillir des preuves, tester dans un environnement autorisé et rapporter précisément le résultat.

Cette synergie doit rester maîtrisée : MemoLibDev ne doit pas devenir plus complexe à maintenir que la valeur qu’il apporte. Toute expérimentation sur MemoLib doit respecter les règles de lecture seule, d’autorisation explicite, de protection des données et de séparation des environnements.

## 13. Décisions et critères de progression

- Le premier produit à tester commercialement est le **contrôleur d’agents IA (B)** ; le guide universel (A) et la plateforme complète (C) restent des évolutions possibles.
- Priorité à une expérience simple : ouvrir un projet, comprendre son état, sélectionner un problème, préparer une correction, vérifier les résultats et laisser l’utilisateur décider de l’application.
- Ne pas engager une expansion importante tant que l’utilité, la sécurité, l’usage récurrent et la volonté de payer ne sont pas étayés.
- Les chiffres d’adoption du marché, les prix, les volumes de clients et les scénarios de chiffre d’affaires doivent être documentés avec des sources datées ou explicitement étiquetés comme hypothèses ; ils ne sont pas des preuves de ventes futures.
