# SPEC-D6.0 — MemoLibDev Agent Loop Specification

Statut : **LOCKED / APPROVED** (verrouillé le 2026-10-06T16:55+02:00).
Aucun code `agent_loop.py` ne doit être écrit sans respecter ce contrat.
La spec ne peut être modifiée que sur découverte d'une contradiction
réelle avec le code D5.

Objet : spécifier l'orchestration des composants D5 (déjà construits et
testés) en un **agent de développement contrôlé, fail-closed**. D6
n'ajoute aucune capacité nouvelle à l'agent : il **orchestre** des
garde-fous existants et prouvés. Il ne peut jamais les contourner.

Principe fondateur :

> L'intelligence appartient à l'IA. L'autorité appartient à l'humain.
> La puissance de l'agent n'augmente que lorsque les mécanismes de
> contrôle ont prouvé qu'ils peuvent la contenir.

---

## 0. Référentiel — composants réels orchestrés (vérifiés D5.4→D5.9)

Cette spec s'ancre sur des contrats EXISTANTS et testés. Aucune
signature inventée.

| Composant | Entrée réelle | Sortie réelle | Statut |
|---|---|---|---|
| `project_target.resolve_target()` | env `MEMOLIBDEV_TARGET` | `ProjectTarget(path, git_root, head, head_full, branch, fingerprint)` ; lève `ProjectTargetError` | D5 Phase A ✅ |
| `decision_agent.inspect_repository()` | cible | `list[dict]` (fichiers + metadata read-only) | ✅ |
| `decision_selector.select_relevant_files(files, request)` | fichiers + requête | `{selected:[{path,score,category,content,...}], candidate_count, context_chars, ...}` | 5F.2 ✅ |
| `evidence_resolver_v2_2.build_store(selected_paths, git_root, target)` | chemins + cible | `list[EvidenceRecord]` liés à git_root+HEAD+fingerprint+SHA256 | ✅ |
| `evidence_resolver_v2_2.resolve(store, query, target)` | store + requête | `list[EvidenceResult(status, path, line_*, evidence, score, reason)]` ; statut `ACCEPTED`/`WEAK_EVIDENCE`/`STALE_EVIDENCE`/`SYMBOL_NOT_FOUND`/`INSUFFICIENT_EVIDENCE` | D5.4 ✅ |
| `import_provenance.resolve_import_reference(...)` | référence d'import | `ProvenanceResult(status, source_path, symbol, module_specifier, resolved_path, reason)` ; statut `RESOLVED`/`EXTERNAL_MODULE`/`MODULE_NOT_FOUND`/`INVALID_ALIAS`/`OUTSIDE_REPOSITORY`/`INVALID_IMPORT` | D5.5 ✅ |
| `coder_authorization.authorize(target, evidence, evidence_result, provenance, allowed_paths, action, human_approval)` | preuves + approbation | `CoderAuthorization(status=AUTHORIZED|REJECTED, ...)` | D5.6 ✅ |
| `coder_authorization.validate_authorization(auth, target, requested_path, allowed_paths)` | certificat | `(bool, reason)` | D5.6 ✅ |
| `controlled_coder.enforce_coder_authorization(auth, target, allowed_paths)` | certificat | `{verdict: AUTHORIZED|REJECT, reason, [authorization]}` | D5.8 ✅ |
| `controlled_coder.enforce_write_guardrail(diff, allowed_paths)` | diff + scope | `{verdict: ACCEPTABLE|REJECT, touched_files, out_of_scope_files}` | 5G ✅ |
| `controlled_coder.verify_patch_in_sandbox(diff, touched_paths, patch_file)` | diff | `{applicable, returncode, sandbox, sandbox_files, ...}` | 5G.1 / D5.8 ✅ |
| `d59_controlled_apply.run_controlled_apply(repo_root, certificate, patch_text, target_head, target_fingerprint, verify)` | certificat + patch | `ApplyResult(status=APPLIED|ROLLED_BACK|BLOCKED, rolled_back, committed, pushed, ...)` | D5.9 ✅ |

---

## 1. Niveaux d'autorité (L1 → L7)

| Niveau | Capacité | Automatique | Garde-fou dominant |
|---|---|---|---|
| **L1** | READ / inspecter | ✅ | confinement cible (`project_target`) |
| **L2** | ANALYZE / sélectionner | ✅ | sélection déterministe |
| **L3** | PLAN / proposer | ✅ | evidence `ACCEPTED` requise |
| **L4** | CODE / produire un patch | ✅ contrôlé | write guardrail + scope |
| **L5** | TEST / vérifier (sandbox) | ✅ | sandbox éphémère, jamais la cible |
| **L6** | APPLY | ❌ **humain obligatoire** | certificat D5.8 + D5.9 |
| **L7** | autonomie complète | ❌ **HORS PÉRIMÈTRE** | — |

Règles d'autorité :
- **Non-escaladable par l'agent.** L'agent ne peut jamais faire passer une
  étape d'un niveau à un niveau supérieur. Seul l'humain autorise L6.
- Transitions interdites même sous demande ambiguë : `L5 → L6` sans
  approbation humaine ; tout `→ L7`.
- Le niveau d'autorité d'une approbation est porté par le certificat
  (`HumanApproval.authority_level`), et `authorize()` **rejette L5/L6**
  comme niveau d'autorité de l'approbation Coder (le Coder reste L3/L4).

---

## 2. Invariants globaux (fail-closed) — valables à TOUTES les étapes

Ces invariants priment sur toute logique d'étape. Toute violation =
`ABORT` immédiat, sans écriture.

0. **CAPACITÉ ≠ AUTORISATION ≠ APPLICATION** (principe fondateur).
   Que l'IA *sache* produire une transformation (capacité) n'implique
   jamais qu'elle soit *autorisée* à la faire (certificat D5.8), ni
   qu'elle soit *appliquée* (D5.9 + humain). Les trois sont des étapes
   distinctes et non fusionnables :
   `IA sait modifier → D6 propose → D5 vérifie → Humain autorise → D5.9 applique`.
   MemoLibDev vise explicitement : *agent capable de proposer n'importe
   quelle transformation, incapable d'en appliquer une sans contrôle.*

1. **Cible unique et vérifiée.** `MEMOLIBDEV_TARGET` résolu une seule fois
   au début ; toutes les étapes partagent le même `ProjectTarget`
   (git_root + HEAD + fingerprint). Pas de fallback silencieux.
2. **Fail-closed par défaut.** Tout statut inconnu / ambigu / absent →
   `BLOCK`, jamais `ALLOW`. (Evidence inconnue → BLOCK ; provenance
   inconnue → BLOCK ; identité cible inconnue → BLOCK ; approbation
   absente → BLOCK.)
3. **Scope immuable.** Le périmètre autorisé = `authorization.path` du
   certificat. Les mêmes `allowed_paths` servent à `enforce_coder_authorization`
   ET à `enforce_write_guardrail`. Jamais d'élargissement.
4. **Continuité cryptographique.** Evidence SHA256 émis en D5.6 doit
   rester identique au contenu courant en D5.9 (`evidence_sha256` ==
   SHA actuel). Toute dérive → BLOCK.
5. **Humain souverain pour L6.** `APPLY` est impossible sans certificat
   `AUTHORIZED` dont `human_approval.approved is True`.
6. **Jamais de COMMIT / PUSH / PRODUCTION automatiques.**
   `automatic_commit = automatic_push = production = False` (constantes
   D5.9). `APPLIED ≠ COMMITTED`.
7. **Jamais d'installation de dépendances dans le vrai dépôt** pour
   vérifier un patch. Le VERIFY complet (npm) s'exécute sur une copie,
   jamais via `npm install` dans la cible.
8. **Aucune auto-modification du Control Plane.** L'agent ne peut pas
   produire de patch touchant les fichiers de contrôle (voir §6).
9. **Journalisation.** Chaque étape émet un enregistrement (métré via le
   contrat 6A `usage_metering`) ; le résultat final est un rapport
   immuable. Rien n'est effacé.

---

## 3. Machine à états de la boucle

```
REQUEST → DECISION → PLAN → EVIDENCE → PROVENANCE → APPROVAL
   → CODER → D5.8 GATES → D5.9 APPLY → VERIFY → RESULT
```

États terminaux possibles à CHAQUE étape :
- `CONTINUE` : passe à l'étape suivante avec les données transmises.
- `BLOCK` : arrêt propre, raison journalisée, aucune écriture.
- `ABORT` : arrêt immédiat sur violation d'invariant global.
- `AWAIT_HUMAN` : suspension jusqu'à décision humaine (uniquement
  APPROVAL ; L6).

Règle : un `BLOCK`/`ABORT` ne peut jamais être « rattrapé » par une
étape ultérieure. La boucle ne redescend jamais d'un verdict négatif
vers un verdict positif.

---

## 4. Spécification étape par étape

Pour chaque étape : **Entrée · Sortie · Contrat · Niveau · Erreurs ·
Arrêt immédiat · Données transmises · Auto vs Humain.**

### 4.1 REQUEST
- **Entrée** : texte libre utilisateur (« corrige X »), nom de la cible.
- **Sortie** : `request_text` normalisé + `ProjectTarget` résolu.
- **Contrat** : `resolve_target()` réussit (dépôt git valide, HEAD lisible).
- **Niveau** : L1.
- **Erreurs** : `ProjectTargetError` (var absente / chemin invalide / non-git).
- **Arrêt immédiat** : cible non résoluble → `ABORT` (invariant 1).
- **Transmis** : `request_text`, `target`.
- **Auto / Humain** : automatique.

### 4.2 DECISION
- **Entrée** : `request_text`, `target`.
- **Sortie** : classification de l'intention + `files = inspect_repository()`.
- **Contrat** : inspection read-only ; aucune écriture ; aucune sortie de
  la cible.
- **Niveau** : L1→L2.
- **Erreurs** : dépôt illisible, aucune intention exploitable.
- **Arrêt immédiat** : si l'intention implique une action interdite (§6)
  → `BLOCK`.
- **Transmis** : `files`, intention.
- **Auto / Humain** : automatique.

### 4.3 PLAN
- **Entrée** : `files`, `request_text`.
- **Sortie** : `selection = select_relevant_files(files, request_text)` →
  `selected[]` (chemins + scores), `allowed_paths` candidat.
- **Contrat** : sélection déterministe, bornée (`MAX_*`), traçable
  (scores + reasons).
- **Niveau** : L3.
- **Erreurs** : sélection vide.
- **Arrêt immédiat** : `selected == []` → `BLOCK` (rien à prouver).
- **Transmis** : `selection`, `allowed_paths`.
- **Auto / Humain** : automatique (proposition seulement).

### 4.4 EVIDENCE
- **Entrée** : `selected` chemins, `target`.
- **Sortie** : `store = build_store(...)` + `results = resolve(store, query, target)`.
- **Contrat** : chaque preuve liée à git_root+HEAD+fingerprint+SHA256.
  Seul `ACCEPTED` est une preuve de déclaration ; `WEAK/STALE/NOT_FOUND`
  ne prouvent rien.
- **Niveau** : L3.
- **Erreurs** : aucune evidence `ACCEPTED`.
- **Arrêt immédiat** : si l'action projetée vise un symbole sans
  `ACCEPTED` → `BLOCK` (invariant 2, fail-closed).
- **Transmis** : `EvidenceRecord` + `EvidenceResult(ACCEPTED)` pour le
  fichier cible.
- **Auto / Humain** : automatique.

### 4.5 PROVENANCE
- **Entrée** : référence d'import vers le symbole cible, `target`.
- **Sortie** : `ProvenanceResult`.
- **Contrat** : `status == RESOLVED` et `resolved_path == fichier cible`.
  Tout autre statut (`EXTERNAL_MODULE`, `MODULE_NOT_FOUND`,
  `INVALID_ALIAS`, `OUTSIDE_REPOSITORY`, `INVALID_IMPORT`) = non autorisable.
- **Niveau** : L3.
- **Erreurs** : provenance non résolue ou vers un autre fichier.
- **Arrêt immédiat** : `status != RESOLVED` → `BLOCK`.
- **Transmis** : `ProvenanceResult(RESOLVED)`.
- **Auto / Humain** : automatique.

### 4.6 APPROVAL  ⟵ **frontière L6, humain obligatoire**
- **Entrée** : `target`, evidence `ACCEPTED`, provenance `RESOLVED`,
  `allowed_paths`, `ActionDossier` (type, risque, réversibilité).
- **Sortie** : `HumanApproval` réel + `CoderAuthorization = authorize(...)`
  avec `status == AUTHORIZED`.
- **Contrat** : les 10 conditions de `authorize()` (scope, evidence
  ACCEPTED, concordance de chemin, intégrité SHA, provenance RESOLVED
  concordante, ActionDossier cohérent, approbation complète, niveau
  d'autorité valide, L5/L6 interdits comme autorité Coder).
- **Niveau** : **L6** (déclenche l'autorité d'appliquer plus tard).
- **Erreurs** : approbation absente/incomplète ; `authorize()` → REJECTED.
- **Arrêt immédiat** : pas d'approbation humaine → `AWAIT_HUMAN` puis, si
  refus/timeout, `BLOCK`. L'agent **ne peut pas** fabriquer
  `human_approval.approved = True`.
- **Transmis** : `CoderAuthorization (AUTHORIZED)` = certificat unique.
- **Auto / Humain** : **HUMAIN**. C'est le seul point où un humain injecte
  de l'autorité. Tout le reste en découle.

### 4.7 CODER
- **Entrée** : certificat `AUTHORIZED`, contenu du fichier autorisé,
  objectif.
- **Sortie** : `diff` (unified) OU `NO_PATCH_POSSIBLE`.
- **Contrat** : le Coder ne lit QUE le(s) fichier(s) du scope ; produit un
  diff minimal ; aucune invention de fichier ; aucun secret ; aucun
  contournement d'auth.
- **Niveau** : L4.
- **Erreurs** : réponse modèle vide/tronquée ; `NO_PATCH_POSSIBLE`.
- **Arrêt immédiat** : `NO_PATCH_POSSIBLE` → `RESULT` (fin propre, pas une
  erreur). Diff absent → `BLOCK`.
- **Transmis** : `diff`.
- **Auto / Humain** : automatique (sous couvert du certificat déjà émis).

### 4.8 D5.8 GATES
- **Entrée** : certificat, `diff`, `allowed_paths` (== scope certificat).
- **Sortie** : verdict combiné :
  1. `enforce_coder_authorization(auth, target, allowed_paths)` == AUTHORIZED
  2. `enforce_write_guardrail(diff, allowed_paths)` == ACCEPTABLE
  3. `verify_patch_in_sandbox(diff, touched, patch_file)` → `applicable == True`
- **Contrat** : les trois maillons alignés (jointures prouvées D5.8).
- **Niveau** : L4→L5.
- **Erreurs** : certificat non AUTHORIZED ; diff hors scope ; patch non
  applicable en sandbox.
- **Arrêt immédiat** : tout maillon négatif → `BLOCK` (aucun apply).
- **Transmis** : `diff` validé + certificat.
- **Auto / Humain** : automatique (sandbox = L5, jamais la cible).

### 4.9 D5.9 APPLY  ⟵ **exécute l'autorité L6 émise en 4.6**
- **Entrée** : `repo_root`, certificat (projeté en `ApplyCertificate`),
  `patch_text`, `target_head`, `target_fingerprint`, callback `verify`.
- **Sortie** : `ApplyResult(status = APPLIED | ROLLED_BACK | BLOCKED)`.
- **Contrat** : `run_controlled_apply()` : pre_apply (target binding +
  evidence SHA + scope + `git apply --check`) → snapshot → `git apply`
  (working tree) → post_apply_or_rollback.
- **Niveau** : **L6**.
- **Erreurs** : pre-apply BLOCK ; apply échoue ; rollback échoue
  (`ROLLBACK_FAILED` = incident majeur).
- **Arrêt immédiat** : BLOCK avant toute écriture si un gate échoue.
- **Transmis** : `ApplyResult`.
- **Auto / Humain** : exécution automatique **de l'autorité déjà
  approuvée** ; aucune nouvelle décision autonome. `commit=push=False`.

### 4.10 VERIFY (deux niveaux)
- **Entrée** : état post-apply (ou sandbox), niveau de risque de l'action.
- **Sortie** : `(ok, reason)` + éventuel déclenchement du VERIFY complet.
- **Contrat** :
  - **VERIFY léger (obligatoire, toujours)** : `git status`, HEAD, SHA des
    fichiers ciblés, scope respecté, tests déterministes ciblés. Rapide.
  - **VERIFY complet (selon risque)** : `npm run type-check`, `lint`,
    `test:ci` — exécuté sur une COPIE, **jamais** via `npm install` dans
    la cible (invariant 7). Déclenché si risque ≥ seuil (ex. ActionDossier
    `risk` = HIGH, ou fichier critique).
- **Niveau** : L5.
- **Erreurs** : échec léger → ROLLBACK immédiat (via D5.9) ; échec complet
  → ROLLBACK + `STOP_HUMAN_REVIEW`.
- **Arrêt immédiat** : `verify` FAIL → D5.9 effectue le rollback
  automatique (SHA initial == final garanti).
- **Transmis** : verdict de vérification.
- **Auto / Humain** : automatique ; l'échec rend la main à l'humain.

### 4.11 RESULT
- **Entrée** : tous les verdicts d'étape.
- **Sortie** : rapport final immuable :
  `{request, target, decision, selection, evidence, provenance,
    authorization, diff, d58_gates, apply_result, verify, final_state}`.
- **Contrat** : état final ∈ {`APPLIED (non commité)`, `ROLLED_BACK`,
  `BLOCKED`, `NO_PATCH_POSSIBLE`, `AWAIT_HUMAN`}. Jamais `COMMITTED`,
  jamais `PUSHED`, jamais `PRODUCTION`.
- **Niveau** : L1 (lecture/rapport).
- **Transmis** : rapport à l'humain pour revue finale (commit = décision
  humaine séparée, hors D6).
- **Auto / Humain** : rapport automatique ; **le commit reste humain**.

---

## 5. VERIFY — matrice de déclenchement

| Risque de l'action | VERIFY léger | VERIFY complet |
|---|---|---|
| LOW (doc, commentaire) | ✅ obligatoire | ⬜ non |
| MEDIUM (logique locale) | ✅ obligatoire | ⚠️ optionnel |
| HIGH (auth, sécurité, données, migration) | ✅ obligatoire | ✅ obligatoire (sur copie) |

Règle dure : **jamais `npm install` dans le vrai dépôt**. Le VERIFY
complet s'exécute dans une copie disposant déjà de ses dépendances, ou
est reporté à une étape CI hors boucle.

---

## 6. Interdictions absolues (NEVER_ALLOW_AGENT)

Indépendamment de tout score/approbation, l'agent ne peut JAMAIS
produire ni appliquer un changement qui :

- cible les fichiers du Control Plane :
  `coder_authorization.py`, `controlled_coder.py` (gates),
  `d59_controlled_apply.py`, `project_target.py`,
  `evidence_resolver_v2_2.py`, `import_provenance.py`, et cette spec ;
- désactive/affaiblit un garde-fou (scope, evidence, approbation) ;
- modifie les règles d'approbation ou le mécanisme de rollback ;
- exfiltre des secrets / credentials ;
- escalade l'autorité (Lx → Lx+1) sans humain ;
- exécute une action juridique autonome (hors périmètre produit) ;
- commit / push / déploie automatiquement.

Toute requête tendant vers l'un de ces points → `BLOCK` dès DECISION.

---

## 7. Ce que `agent_loop.py` minimal devra implémenter (après verrouillage)

Portée MINIMALE du premier code (ne pas dépasser) :
1. Orchestrer les 11 étapes dans l'ordre, en passant les données
   transmises décrites au §4.
2. Appeler UNIQUEMENT les composants réels du §0 (aucune réimplémentation).
3. Respecter la machine à états §3 (BLOCK/ABORT non rattrapables).
4. Point d'injection humain unique en 4.6 (APPROVAL).
5. Produire le rapport immuable §4.11.
6. Pour le premier run : cible = **sandbox éphémère** (comme D5.9), pas
   MemoLib ; VERIFY léger uniquement.

Hors portée du premier code : VERIFY complet npm, multi-fichiers,
agents spécialisés, hooks, steering. (Niveaux ultérieurs.)

### 7.1 Feuille de route D6 (positionnement du code à venir)

| Étape | Objectif | Priorité |
|---|---|---|
| **D6.0** | Contrat Agent Loop universel (ce document) | 🔴 |
| **D6.1** | `FileTarget` générique + résolution d'adaptateur | 🔴 |
| **D6.2** | `code_adapter` (cas textuel, chaîne D5 complète) | 🔴 |
| **D6.3** | `xlsx_adapter` + premier cas « planning » | 🔴 |
| **D6.4** | VERIFY XLSX (non-corruption, formules, données métier) | 🔴 |
| **D6.5** | `docx_adapter` (procédures, courriers) | 🟠 |
| **D6.6** | `pdf_adapter` (read/OCR/extract → structure → nouveau PDF) | 🟠 |
| **D6.7** | Multi-fichiers (transformation cohérente d'un ensemble) | 🟠 |
| **D7** | Agent réellement opérationnel | 🟢 |

Note de direction : le premier **démonstrateur hors code** visé est un
**planning Excel** (D6.3) — plus probant qu'un `.txt` et riche en cas
métier (horaires, chevauchements, répartition, formules). Mais le
`code_adapter` (D6.2) reste le premier adaptateur implémenté car il
réutilise directement la chaîne D5.8/D5.9 déjà prouvée (diff + git).

MemoLibDev se positionne ainsi comme **moteur universel de
transformation contrôlée de ressources** (D5 = sécurité commune,
adaptateurs par format, D6 = cerveau), indépendant du domaine juridique.
MemoLib utilisera ses Legal Packs ; MemoLibDev reste le moteur
d'ingénierie généraliste.

---

## 7bis. Conception FORMAT-AGNOSTIC (cap d'architecture)

D6 doit être conçu dès maintenant pour ne PAS être enfermé dans « agent
qui modifie du Python ». La **première implémentation** reste limitée au
code, mais les contrats sont génériques. Principe : **agent générique +
adaptateurs de format** (même logique que les Legal Packs de MemoLib :
moteur générique + modules spécialisés).

### 7bis.1 Contrat `FileTarget` générique

Remplace la notion implicite « fichier source » par un contrat commun à
tous les formats :

```
FileTarget:
    path            # chemin relatif dans la cible (identique pour tous)
    format          # extension/format logique (ts, py, xlsx, docx, pdf...)
    kind            # CODE | DATA | DOC | SHEET | SLIDES | PDF | IMAGE | BINARY
    size            # taille en octets
    adapter         # nom de l'adaptateur responsable
    content_sha256  # SHA-256 du CONTENU BRUT (octets) — déjà format-agnostic
    git_root        # racine cible (hérité de ProjectTarget)
    git_head        # HEAD de la cible (continuité D5.8/D5.9)
    permissions     # lecture/écriture autorisées sur ce FileTarget
    scope           # périmètre autorisé (unité(s) modifiable(s))
    risk_level      # LOW | MEDIUM | HIGH (pilote la matrice VERIFY §5)
    is_textual      # bool : un diff textuel est-il applicable ?
```

MemoLibDev ne pense plus « je dois modifier `foo.py` » mais « je dois
**transformer cette ressource selon cette intention, dans ce périmètre
précis** ». `FileTarget` est le concept central qui porte cette bascule.

Point clé de compatibilité : **D5.4→D5.9 raisonnent déjà sur
`content_sha256` du contenu**, qui est intrinsèquement format-agnostic
(c'est un hash d'octets). L'identité de preuve, le target binding, le
scope et l'intégrité restent donc valides pour xlsx/docx/pdf **sans
modification**.

### 7bis.2 Ce qui change selon `is_textual`

| | Textuel (code, md, json, csv, txt, yaml) | Binaire (xlsx, docx, pptx, pdf, image) |
|---|---|---|
| EVIDENCE | symbole/ligne via `resolve()` | unité structurée (feuille/cellule, paragraphe, page) via l'adaptateur |
| PATCH | unified diff + `git apply --check` | **transformation vérifiable** produite par l'adaptateur (nouveau contenu + description du changement) |
| D5.8 sandbox | `git apply --check` | application de la transformation sur une COPIE + re-sérialisation |
| D5.9 apply | `git apply` working tree | écriture du nouveau contenu + snapshot/rollback par `content_sha256` |
| VERIFY léger | SHA/scope/structure | validation structurelle de l'adaptateur (pas de corruption) |

Le diff textuel + `git apply` n'est donc **qu'un cas particulier** (le
`code_adapter`). D5.9 reste valide car son rollback repose sur le
snapshot `content_sha256` (restaurer les octets d'origine), pas
spécifiquement sur `git apply -R`.

### 7bis.3 Contrat d'adaptateur de format

Chaque adaptateur expose le même contrat à 5 opérations, et **D6 ne
connaît aucun détail de format** :

```
Adapter:
    read(file_target)      -> contenu structuré (en mémoire)
    analyze(content)       -> compréhension (feuilles/paragraphes/pages...)
    plan(content, intent)  -> changements proposés (traçables)
    modify(content, plan)  -> nouveau contenu (NON écrit)
    validate(old, new)     -> (ok, reason) : pas de corruption, contraintes
```

`modify()` **ne touche jamais le disque** : il retourne un nouveau
contenu que D5.9 appliquera sous certificat + approbation. L'adaptateur
ne contourne aucun garde-fou — il ne fait que **traduire** un format en
unités que la chaîne D5 peut prouver.

### 7bis.4 Arborescence cible (non créée en D6.0)

```
format_adapters/
    code_adapter.py      # cas particulier : diff + git apply  (SEUL en v1)
    xlsx_adapter.py      # feuilles/cellules/formules          (ultérieur)
    docx_adapter.py      # paragraphes/tableaux                (ultérieur)
    csv_adapter.py       # lignes/colonnes, données métier      (ultérieur)
    pptx_adapter.py / pdf_adapter.py / image_adapter.py        (ultérieur)
```

### 7bis.5 Impact sur la première implémentation

- `agent_loop.py` v1 : **uniquement `code_adapter`** (textuel), cible
  sandbox éphémère. Mais les signatures passent déjà `FileTarget` et un
  `adapter`, pour que l'ajout d'un format futur n'exige **aucune**
  modification du cœur D6.
- Les formats binaires sont **hors périmètre v1** mais le contrat est
  réservé. Aucun adaptateur binaire ne sera branché avant d'avoir été
  falsifié de façon adversariale (comme D5.4), notamment sur la
  non-corruption et la préservation des données métier (ex. CSV : « ne
  pas modifier les données » devient un invariant d'adaptateur).

### 7bis.6 Invariants spécifiques aux formats

- Un adaptateur ne peut **jamais** écrire sur disque ; seul D5.9 écrit.
- `content_sha256` reste la source d'intégrité (snapshot/rollback).
- Pour les données métier (CSV/xlsx), l'adaptateur doit prouver que les
  cellules/valeurs hors scope sont **inchangées** (équivalent du write
  guardrail, au niveau cellule).
- Un échec de `validate()` → traité comme un VERIFY FAIL → ROLLBACK D5.9.

---

## 8. Critère de verrouillage de D6.0

La spec est « verrouillée » quand :
- [ ] chaque étape §4 référence un contrat réel du §0 (fait) ;
- [ ] les invariants §2 sont cohérents avec D5.4→D5.9 (auto-audit : fait,
      L5/L6 rejetés par `authorize` L422-423 ; `AUTOMATIC_COMMIT/PUSH/
      PRODUCTION = False` d59 L118-120 ; guardrail `out_of_scope` REJECT ;
      `authorize` exige `ProvenanceStatus.RESOLVED`) ;
- [ ] L6 = seul point humain, non contournable (fait) ;
- [ ] aucune étape ne peut élargir le scope du certificat (fait) ;
- [ ] contrats `FileTarget` + adaptateurs format-agnostic définis sans
      casser D5.8/D5.9 (fait, §7bis — `content_sha256` reste la source
      d'intégrité commune) ;
- [ ] validation humaine explicite de ce document.

Tant que ce document n'est pas validé, **aucun `agent_loop.py` n'est écrit.**
```
