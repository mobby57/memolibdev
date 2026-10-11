# Spec - Moteur de delais CESEDA

**Version :** 0.1 (brouillon)
**Date :** 11/10/2026
**Statut :** EN ATTENTE DE VALIDATION JURIDIQUE
**Auteur technique :** MemoLibDev
**Validation juridique :** a designer (avocat du pilote)

> **Regle directrice**
> Mieux vaut signaler une incertitude que produire une echeance juridiquement
> fausse avec une apparence de certitude.

---

## 1. Objet du document

Ce document specifie le comportement cible d'un moteur de calcul de delais
CESEDA. Il ne contient **aucune regle juridique validee**. Il liste :

- Les defauts constates dans l'implementation actuelle (audit read-only).
- L'interface technique cible.
- Les **questions ouvertes** a faire trancher par l'avocat.
- Les criteres d'acceptation du systeme.

Toute regle juridique citee ici est presentee comme **hypothese a valider**,
jamais comme verite etablie.

---

## 2. Constats d'audit (implementation actuelle)

Audit read-only du fichier `src/lib/legal/ceseda-deadlines.ts`.

| ID | Criticite | Constat | Preuve attendue |
|----|-----------|---------|-----------------|
| C1 | BLOQUANT | "1 mois" code en 30 jours ; "2 mois" code en 60 jours | A verifier sur pieces |
| C2 | MAJEUR | Regle des 48 h appliquee a toute OQTF sans distinction | A verifier sur pieces |
| C3 | MAJEUR | Report au prochain jour ouvre sur tous les delais | A verifier sur pieces |
| C4 | MAJEUR | Type de dossier inconnu -> liste vide, pas d'erreur | A verifier sur pieces |
| C5 | MAJEUR | L'echeance ne porte ni source, ni version, ni certitude | A verifier sur pieces |
| C6 | IMPORTANT | Aucune distinction selon la date de la decision | A verifier sur pieces |
| C7 | IMPORTANT | Calcul en ms (jour = 86 400 000) | A verifier sur pieces |

**Ce que ces constats ne disent pas :**
- Quelles sont les regles correctes.
- Pour qui ces regles s'appliquent.
- Avec quelle source officielle.
- A quelle date ces regles sont en vigueur.

---

## 3. Moteur cible - separation des responsabilites

Quatre composants, quatre responsabilites distinctes.

### 3.1 IA d'extraction

**Role :** extraire les faits d'un document (date de notification, mode de
notification, fondement juridique cite, pieces jointes).

**Interdit :** presenter une information supposee comme un fait etabli.

### 3.2 Moteur de qualification

**Role :** identifier les hypotheses procedurales possibles a partir des faits
verifies.

**Interdit :** choisir arbitrairement une procedure lorsque plusieurs restent
possibles. Doit retourner **plusieurs** hypotheses, ou `INDETERMINABLE`.

### 3.3 Moteur juridique deterministe

**Role :** appliquer des regles **validees, versionnees, sourcees** aux faits
pertinents.

**Interdit :**
- Inventer une regle.
- Completer silencieusement une donnee absente.
- Utiliser une regle non validee par un juriste.

### 3.4 Validation humaine

**Role :** presenter le raisonnement, les sources, les incertitudes et le
resultat propose a l'avocat.

**Interdit :** masquer les reserves ou transformer une suggestion en decision
juridique autonome.

---

## 4. Interface technique cible

### 4.1 Type `CesedaDeadline`

    interface CesedaDeadline {
      id: string;
      type: string;
      label: string;

      // Resultat
      dueDate: string | null;         // ISO 8601, null si indeterminable
      certainty: "confirmed" | "probable" | "indeterminable";

      // Point de depart EXPLICITE
      fromDate: string;               // ISO 8601, jamais implicite
      fromDateSource: string;         // "notification", "publication", etc.

      // Duree
      unit: "days" | "months" | "hours";
      count: number;

      // Traçabilite
      source: {
        text: string;                 // "CESEDA L.614-1"
        version: string;              // "en vigueur au 2026-10-11"
        url?: string;
      };
      rationale: string;              // explication du calcul

      // Controles
      exceptionsChecked: string[];    // ["weekend", "ferie", "changement-heure"]
      requiresHumanReview: boolean;

      // Historique
      ruleVersion: string;            // ex : "2026-10-01"
      validatedBy: string | null;     // nom de l'avocat valideur
      validatedAt: string | null;     // ISO 8601
    }

### 4.2 Politique d'abstention

Si **une seule** des conditions suivantes est vraie :

- Le type de dossier n'est pas reconnu.
- La date de notification n'est pas connue avec certitude.
- Le fondement juridique n'est pas etabli.
- Plusieurs regimes restent plausibles et non tranches.
- La regle applicable n'est pas validee par l'avocat.

Alors :

    dueDate = null
    certainty = "indeterminable"
    requiresHumanReview = true

**Message utilisateur :**
> Echeance non determinable de maniere fiable - verification juridique requise.

### 4.3 Politique d'erreur

- Type inconnu -> **erreur explicite**, pas de liste vide.
- Donnee manquante -> **erreur explicite**, pas de valeur par defaut.
- Regle non validee -> **refus**, pas d'application.

---

## 5. Questions a faire trancher par l'avocat

**Aucune de ces questions n'a de reponse dans ce document.** Elles doivent
etre validees une par une.

### Q1 - Calcul des mois

- Un delai "d'un mois" court-il de date a date ?
- Si oui, comment traiter le 31 janvier + 1 mois ?
- Comment traiter le 29 fevrier ?
- Existe-t-il des cas ou "1 mois" = 30 jours fixes ?

### Q2 - Point de depart

- Le point de depart est-il toujours la date de notification ?
- Existe-t-il des cas ou c'est la date de publication ?
- Existe-t-il des cas ou c'est la date de remise en main propre ?
- Comment traiter une notification par voie postale ?

### Q3 - Report au jour ouvre

- Pour quels delais le report s'applique-t-il ?
- Pour quels delais ne s'applique-t-il **jamais** ?
- Si le dernier jour tombe un samedi, que se passe-t-il ?
- Si le dernier jour tombe un jour ferie, que se passe-t-il ?

### Q4 - Delai de 48 h

- Dans quels cas s'applique-t-il ?
- Dans quels cas ne s'applique-t-il plus ?
- Le delai de 48 h est-il prorogeable ou non ?

### Q5 - Delai de 7 jours

- Dans quels cas s'applique-t-il ?
- Est-il prorogeable ou non ?

### Q6 - Distinction selon la date

- Y a-t-il des regimes transitoires ?
- Depuis quelle date le regime actuel s'applique-t-il ?
- Quelle source officielle fixe ce regime ?

### Q7 - Distinction selon le fondement

- Quels sont les fondements d'OQTF ?
- Chaque fondement a-t-il un regime de recours distinct ?
- Quels sont les regimes speciaux ?

### Q8 - Retention vs assignation vs libre

- Le regime de delai depend-il de la situation administrative ?
- Comment traiter un changement de situation en cours de delai ?
- Comment traiter une nouvelle notification ?

### Q9 - Evenements posterieurs

- Une nouvelle decision change-t-elle le delai initial ?
- Un recours deja introduit modifie-t-il les delais restants ?
- Une decision juridictionnelle modifie-t-elle le calcul ?

### Q10 - Changement d'heure

- Comment traiter un calcul sur les heures lors d'un changement d'heure ?
- Le calcul en millisecondes est-il acceptable si le fuseau est explicite ?

---

## 6. Corpus de reference

**Objectif : 100 scenarios selectionnes, pas 1000 generes.**

Repartition proposee :

| Groupe | Nombre | Objectif |
|--------|-------:|----------|
| Situations de base | 20 | Verifier les parcours ordinaires |
| Variantes de notification | 20 | Detecter les erreurs d'extraction |
| Changements de situation | 20 | Verifier la requalification |
| Regimes speciaux | 15 | Reperer les regles non generalisables |
| Dossiers incomplets | 15 | Verifier l'abstention |
| Cas adversariaux | 10 | Verifier le refus de conclure |

**Chaque scenario doit contenir :**

1. Les faits et pieces de reference.
2. Les faits certains, contestes, inconnus.
3. La qualification attendue (ou les qualifications possibles).
4. Les textes officiels applicables a la date consideree.
5. Le raisonnement attendu.
6. Le resultat attendu et les calculs.
7. Les informations supplementaires a demander.
8. Les cas ou le systeme doit s'abstenir.
9. La validation et les reserves de l'avocat.

**Le corpus ne doit pas etre constitue uniquement par le LLM.**
L'avocat valide les reponses attendues et les cas limites.

---

## 7. Criteres d'acceptation

Le systeme est **pret pour le pilote** uniquement si :

1. **Aucune erreur critique non resolue** dans le corpus de reference valide.
2. **Tracabilite complete** : source, version, disposition, date de validation.
3. **Abstention correcte** : toutes les situations indeterminables affichent
   le message d'abstention, pas une date fausse.
4. **Refus explicite** : aucune donnee manquante n'est completee par defaut.
5. **Corpus de reference** : 100 scenarios valides par l'avocat.
6. **Revue croisee** : au moins 10 scenarios analyses independamment par
   l'avocat et le systeme, avec comparaison documentee.

**Le systeme n'est pas pret** simplement parce que 100 scenarios passent.
Il est pret quand **l'avocat a valide le corpus** et que **les cas limites
sont documentes**.

---

## 8. Ordre d'execution

| Priorite | Action | Blocage |
|----------|--------|---------|
| P0 | Audit read-only complet | Manque 2 fichiers |
| P1 | Validation juridique des questions Q1-Q10 | Avocat |
| P2 | Construction du corpus de 100 scenarios | Avocat + temps |
| P3 | Implementation du moteur versionne | P1 validee |
| P4 | Diff minimal + tests | P2 validee |
| P5 | Test sur copie isolee | P3 fait |
| P6 | Pilote limite avec l'avocat | P5 fait |
| P7 | Extension progressive | P6 concluant |

**Regle :** aucune ligne de code du moteur juridique n'est ecrite avant que
Q1-Q10 soient tranchees par l'avocat.

---

## 9. Ce que ce document n'est pas

- Un avis juridique.
- Un jeu de regles validees.
- Une garantie de conformite.
- Un substitut a la validation par un avocat.

---

## 10. Prochaine action

1. **Avocat** : lire les questions Q1-Q10, repondre par ecrit, designer une
   personne responsable de la validation.
2. **Technique** : collecter les 2 fichiers manquants
   (`workingDays.ts`, `create-dossier/route.ts`), produire l'audit complet.
3. **Puis** : decision conjointe sur l'implementation.

---

*Document vivant. Toute regle ajoutee doit citer sa source, sa version et son
valideur. Une regle sans ces trois elements ne peut pas etre appliquee.*
