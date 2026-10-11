# CESEDA - Specification du moteur de regles versionnees

**Statut :** BROUILLON A RELIRE - aucune regle juridique de ce document n'est validee.
**Date de redaction :** 11/10/2026
**Perimetre :** OQTF et leurs delais de recours (premier pilote).

> Ce document decrit la cible (architecture, donnees, comportements). Il ne modifie aucun code.

---

## 1. Objectif

Remplacer le calcul de delais actuel (jours ajoutes a une date, valeurs ecrites en dur) par un moteur qui :

1. identifie la situation a partir de faits verifies ;
2. applique une regle sourcee, versionnee et validee par l'avocat ;
3. signale l'incertitude et s'abstient quand il ne peut pas conclure ;
4. conserve de quoi justifier chaque resultat.

**Principe directeur :** mieux vaut afficher non determinable qu'une echeance fausse presentee comme certaine.

---

## 2. Principes non negociables

- Le LLM n'applique aucune regle et ne fixe aucun delai. Il peut extraire des faits d'un document ; ces faits restent declares tant qu'ils ne sont pas confirmes.
- Aucune date n'est affichee sans regle dont le statut est valide_avocat pour la date de la decision.
- Echec ferme : donnee absente, regle absente, type inconnu ou contradiction -> pas de date.
- Chaque resultat est une proposition soumise a l'avocat, jamais un acte opposable.
- Aucune duree de ce document n'est une regle : les valeurs sont a renseigner par l'avocat a partir des textes officiels.

---

## 3. Constats de l'audit qui motivent cette specification

### Delais (fichier ceseda-deadlines.ts)

| Ref. | Constat |
|------|---------|
| C1 | 1 mois et 2 mois codes en 30 et 60 jours : date parfois trop tardive. |
| C2 | Regle des 48 h appliquee a toute OQTF sans delai ; cas des 7 jours absent. |
| C3 | Report au jour ouvre applique a tous les delais, y compris 48 h et 24 h. |
| C4 | Type de dossier inconnu -> liste vide, sans erreur. |
| C5 | Resultat sans source, sans version, sans niveau de certitude ; point de depart non defini. |
| C6 | Aucune distinction selon la date de la decision. |
| C7 | Calcul en millisecondes (jour = 86 400 000 ms). |

### Analyseur IA (ceseda-analyzer.ts, ceseda-intake.ts)

| Ref. | Constat |
|------|---------|
| A1-A2 | @ts-nocheck ; sortie du LLM non validee ; modele 3B par defaut. |
| A3 | Probabilite de succes inventee ; repli non distingue d'une analyse. |
| A4 | Second moteur de delais dans l'analyseur, divergent du premier. |
| A6 | Trois vocabulaires de types de procedure (casse differente). |
| Q2 | Mode de notification, mentions de recours, date de la decision, aide juridictionnelle en cours : non saisis comme donnees. |

**Non lus a ce jour :** workingDays.ts, create-dossier/route.ts, CopilotCeseda.tsx, ingest-ceseda.ts, les tests.

---

## 4. Modele de donnees

### 4.1 Faits d'entree (CaseFacts)

Chaque fait porte un statut et une provenance :

    Fact<T> {
      value: T | null
      status: "confirme" | "declare" | "inconnu" | "contradictoire"
      source: { documentId, extraitOuPage } | "saisie_avocat" | "saisie_client"
    }

Faits minimaux pour une OQTF :

| Fait | Remarque |
|------|----------|
| dateDecision | Distincte de la notification. Sert a choisir le regime temporel. |
| dateNotification + heureNotification | L'heure compte si un delai est exprime en heures. |
| modeNotification | Remise en main propre, recommande, affichage, notification en retention, autre, inconnu. |
| mentionsVoiesEtDelaisDeRecours | Presentes / absentes / inconnues. |
| decisionsContenues[] | Une meme decision ecrite peut en contenir plusieurs. Chacune est qualifiee separement. |
| situationPersonne | Libre, assignee a residence, en retention, inconnue. |
| evenements[] | Nouvelle decision, assignation notifiee, recours deja depose, etc. |

### 4.2 Regle (Rule)

    Rule {
      id, version
      procedure: "OQTF"
      conditions: predicat sur CaseFacts
      effectiveFrom, effectiveTo
      startEvent: "notification" | "decision" | autre   // A FAIRE TRANCHER
      duration: { unit: "heures" | "jours" | "mois", value }   // A RENSEIGNER PAR L'AVOCAT
      computation: {
        franc: true | false                            // A FAIRE TRANCHER
        prorogationJourOuvre: true | false             // par regle, jamais globale
        notes
      }
      legalSources: [{ reference, url, versionDate, consultedAt }]
      validationStatus: "a_verifier" | "valide_avocat" | "obsolete"
      validatedBy, validatedAt
      changelog[]
    }

Un registre de regles est un ensemble de fichiers JSON versionnes dans le depot, relus et valides avant fusion.

### 4.3 Resultat (DeadlineResult)

    DeadlineResult {
      etat: "DETERMINE" | "SOUS_RESERVE" | "NON_DETERMINABLE"
      dueAt: date-heure (fuseau Europe/Paris) | null
      ruleId, ruleVersion
      startEventUtilise
      hypotheses[]
      faitsManquants[]
      avertissements[]
      validationAvocatRequise: true
      trace: etapes du calcul
    }

Ce type remplace { type, label, dueDate }. dueDate ne peut plus exister seul.

---

## 5. Regles de calcul (algorithme, sans valeurs juridiques)

Le calcul est pilote par la regle, pas par le code :

1. Choisir la regle : celles dont conditions sont satisfaites et dont la periode effectiveFrom/effectiveTo contient la date de la decision. Zero regle ou plusieurs regles plausibles -> NON_DETERMINABLE.

2. Determiner le point de depart selon startEvent. Fait absent ou non confirme -> NON_DETERMINABLE (ou SOUS_RESERVE si la regle l'autorise explicitement).

3. Ajouter la duree par unite :
   - mois : de date a date, en dates calendaires locales ;
   - jours : franc ou non selon la regle ;
   - heures : calcul en heures locales, avec gestion des changements d'heure.

4. Appliquer la prorogation au jour ouvre si prorogationJourOuvre=true dans la regle.

5. Tracer : chaque etape, chaque hypothese, chaque exception examinee.

---

## 6. Politique d'abstention

Resultat NON_DETERMINABLE si au moins une condition :

- dateNotification absente ou contradictoire ;
- modeNotification inconnu et la regle en depend ;
- type de decision inconnu ;
- situation de la personne inconnue ;
- plusieurs regimes plausibles ;
- aucune regle valide_avocat pour la date de la decision ;
- regle a_verifier ou obsolete.

Resultat SOUS_RESERVE si une regle valide s'applique mais repose sur une hypothese.

**Message affiche pour l'abstention :**
> Echeance non determinable de maniere fiable - verification juridique requise.

Suivi de la liste des faits manquants.

---

## 7. Politique d'erreur (echec ferme)

- Type de procedure inconnu : erreur explicite, jamais une liste vide.
- Un seul vocabulaire de types, issu de l'enumeration ProcedureType.
- Exception pendant le calcul : aucun resultat de date ; journalisation ; message a l'avocat.
- Interdiction de tout repli qui renvoie des valeurs par defaut sans l'indiquer.
- Un second moteur ne doit pas exister : un seul point d'entree.

---

## 8. Separation des roles

| Composant | Role | Interdit |
|-----------|------|----------|
| Extraction (IA) | Proposer des faits a partir des pieces | Fixer un delai, citer un article comme certain |
| Qualification | Lister les situations possibles | Choisir arbitrairement entre plusieurs regimes |
| Moteur deterministe | Appliquer la regle validee | Inventer une regle ou combler une donnee absente |
| Avocat | Valider faits, regle, resultat | - |

Dans l'analyseur IA : retirer les champs successProbability et les delais produits par le modele.

---

## 9. Questions a faire trancher par l'avocat

A traiter a partir des textes officiels consolides (Legifrance).

1. Quels regimes s'appliquent selon la date de la decision (reforme de 2024 et modifications ulterieures) ? Existe-t-il des dispositions transitoires ?
2. OQTF avec delai de depart volontaire : duree, unite, point de depart.
3. OQTF sans delai de depart volontaire, hors retention et assignation : duree, unite, point de depart.
4. Assignation a residence : duree du recours ; effet sur un delai deja en cours.
5. Retention : duree du recours et delai de jugement.
6. Chaque delai est-il franc ou non ?
7. Pour quels delais la prorogation au jour ouvre s'applique-t-elle, et pour lesquels est-elle exclue ?
8. Notification irreguliere ou absence de mention des voies et delais de recours : effet sur le delai.
9. Effet d'une demande d'aide juridictionnelle, d'un recours gracieux ou hierarchique sur le delai.
10. Interdiction de retour : delais applicables.
11. Refere liberte, refere suspension : distinguer le delai pour agir du delai dans lequel le juge statue.
12. Computation d'un mois : confirmer la regle de date a date.
13. Quelles references jurisprudentielles du depot peuvent etre conservees ?

---

## 10. Tests (sans Ollama)

**Calculatrice :**
- fin de fevrier, annee bissextile et non bissextile ;
- mois de 30 et de 31 jours (date a date) ;
- echeance un samedi, un dimanche, un jour ferie, un pont ;
- changements d'heure (dernier dimanche de mars et d'octobre) ;
- notification a 23 h 59 et a minuit ;
- delais en heures sur plusieurs jours.

**Abstention :** un test par condition de la section 6.

**Echec ferme :** type inconnu, regle absente, regle a_verifier, exception.

**Versionnement :** meme dossier avec date de decision avant et apres un changement de regime.

**Non-regression :** jeu de dossiers comparant l'ancien moteur et le nouveau.

**Criteres d'acceptation :**
- aucune sortie DETERMINE sans regle valide_avocat ;
- aucune date quand l'etat est NON_DETERMINABLE ;
- 100 % des cas du corpus valide par l'avocat conformes ;
- chaque resultat conserve une trace complete.

---

## 11. Migration (hors de ce document)

- Pas de modification de code sans autorisation explicite et diff relu.
- Ordre envisage : registre de regles vides -> calculatrice et tests -> abstention -> remplacement des appelants -> suppression de extractDeadlines.
- Aucune regle n'est mise en production avant validation par l'avocat.

---

## 12. Limites de ce brouillon

- Je ne suis pas avocat ; ce document n'etablit aucune regle de droit.
- Legifrance n'a pas pu etre consulte directement ; les sources secondaires trouvees sont contradictoires.
- Les fichiers workingDays.ts et l'appelant principal n'ont pas ete lus.
- Les references citees dans ceseda-intake.ts n'ont pas ete verifiees.
