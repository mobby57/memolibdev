from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    content_sha256,
    validate_record,
)
from import_provenance import ProvenanceStatus, ProvenanceResult
from project_target import ProjectTarget


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"


class AuthorityLevel(str, Enum):
    L0_OBSERVE = "L0_OBSERVE"
    L1_READ = "L1_READ"
    L2_ANALYZE = "L2_ANALYZE"
    L3_PROPOSE = "L3_PROPOSE"
    L4_PREPARE_ACTION = "L4_PREPARE_ACTION"
    L5_EXECUTE_ACTION = "L5_EXECUTE_ACTION"
    L6_CRITICAL_ACTION = "L6_CRITICAL_ACTION"


@dataclass(frozen=True)
class AuthorizationTarget:
    git_root: str
    head: str
    repository_fingerprint: str


@dataclass(frozen=True)
class HumanApproval:
    approved: bool
    approver: str
    approved_at: str
    authority_level: str
    # V0.4.1 — binding cryptographique de la décision humaine au diff exact.
    # ADDITIF, défaut None : toute HumanApproval existante reste valide et
    # inchangée (rétro-compatibilité des contrats d'autorisation et des
    # versions antérieures de proposition/confiance).
    # Quand ces champs sont renseignés, la décision humaine est liée à UNE
    # proposition précise (proposal_id) et au SHA-256 des OCTETS EXACTS du
    # patch approuvé (expected_diff_sha256). Le binding n'est VÉRIFIÉ que
    # lorsque expected_diff_sha256 est fourni (fail-closed à la vérification),
    # jamais fabriqué ici.
    proposal_id: str | None = None
    expected_diff_sha256: str | None = None
    # V0.4.4-A — expiration explicite (ISO 8601) de la décision humaine.
    # ADDITIF, défaut None. Si None, l'expiration est dérivée de approved_at
    # + APPROVAL_TTL_SECONDS (durée par défaut contrôlée). La vérification se
    # fait au DERNIER point de contrôle avant application (agent_loop §4.8bis),
    # fail-closed. Jamais fabriqué ici.
    expires_at: str | None = None


@dataclass(frozen=True)
class ActionDossier:
    action_id: str
    action_type: str
    target_path: str
    risk: str
    reversibility: str


@dataclass(frozen=True)
class CoderAuthorization:
    path: str
    target: AuthorizationTarget
    evidence_status: str
    evidence_sha256: str
    provenance_status: str
    provenance_source_path: str | None
    provenance_resolved_path: str | None
    action: ActionDossier
    human_approval: HumanApproval
    human_validation_required: bool
    status: str
    reason: str


def _target_from_project(target: ProjectTarget) -> AuthorizationTarget:
    return AuthorizationTarget(
        git_root=str(target.git_root),
        head=target.head_full,
        repository_fingerprint=target.fingerprint,
    )


def _same_target(
    authorization: CoderAuthorization,
    target: ProjectTarget,
) -> bool:
    expected = _target_from_project(target)

    return (
        authorization.target.git_root == expected.git_root
        and authorization.target.head == expected.head
        and authorization.target.repository_fingerprint
        == expected.repository_fingerprint
    )


def _normalize_path(path: str) -> str:
    return str(Path(path)).replace("\\", "/").lstrip("./")


def _reject(
    *,
    path: str,
    target: ProjectTarget,
    evidence: EvidenceRecord,
    provenance: ProvenanceResult | None,
    reason: str,
    action: ActionDossier,
    human_approval: HumanApproval,
) -> CoderAuthorization:
    base_target = _target_from_project(target)

    provenance_status = (
        provenance.status.value
        if provenance is not None
        and hasattr(provenance.status, "value")
        else str(provenance.status)
        if provenance is not None
        else "NOT_PROVIDED"
    )

    return CoderAuthorization(
        path=path,
        target=base_target,
        evidence_status=EvidenceStatus.STALE_EVIDENCE,
        evidence_sha256=evidence.content_sha256,
        provenance_status=provenance_status,
        provenance_source_path=(
            provenance.source_path if provenance is not None else None
        ),
        provenance_resolved_path=(
            provenance.resolved_path if provenance is not None else None
        ),
        action=action,
        human_approval=human_approval,
        human_validation_required=True,
        status=AuthorizationStatus.REJECTED.value,
        reason=reason,
    )


def authorize(
    *,
    target: ProjectTarget,
    evidence: EvidenceRecord,
    evidence_result: EvidenceResult | None,
    provenance: ProvenanceResult | None,
    allowed_paths: list[str],
    action: ActionDossier,
    human_approval: HumanApproval,
) -> CoderAuthorization:
    """
    Construit une autorisation strictement bornée.

    Conditions nécessaires :

      1. EvidenceRecord intègre et actuelle.
      2. EvidenceResult explicitement ACCEPTED.
      3. EvidenceResult.path == EvidenceRecord.path.
      4. Provenance RESOLVED.
      5. Provenance vers le même fichier.
      6. Fichier dans le scope déterministe.
      7. ActionDossier cohérent avec le fichier.
      8. HumanApproval complète et approuvée.
      9. Niveau d'autorité explicitement déclaré.

    Cette fonction ne modifie aucun fichier.
    """

    path = _normalize_path(evidence.normalized_path)

    normalized_allowed = {
        _normalize_path(item)
        for item in allowed_paths
    }

    # 1. Scope déterministe obligatoire.
    if path not in normalized_allowed:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "Le chemin n'est pas présent dans le scope "
                "déterministe autorisé."
            ),
            action=action,
            human_approval=human_approval,
        )

    # 2. EvidenceResult obligatoire.
    if evidence_result is None:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="EvidenceResult absent.",
            action=action,
            human_approval=human_approval,
        )

    # 3. Le résultat de résolution doit être ACCEPTED.
    if evidence_result.status != EvidenceStatus.ACCEPTED:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "EvidenceResult non ACCEPTED: "
                f"{evidence_result.status}."
            ),
            action=action,
            human_approval=human_approval,
        )

    # 4. Le résultat accepté doit pointer vers le même fichier.
    result_path = (
        _normalize_path(evidence_result.path)
        if evidence_result.path
        else None
    )

    if result_path != path:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "EvidenceResult path ne correspond pas "
                "au fichier d'évidence."
            ),
            action=action,
            human_approval=human_approval,
        )

    # 5. Intégrité cryptographique obligatoire.
    valid, reason = validate_record(evidence, target)

    if not valid:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=f"Evidence invalide: {reason}",
            action=action,
            human_approval=human_approval,
        )

    if not evidence.content:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="Evidence vide.",
            action=action,
            human_approval=human_approval,
        )

    # 6. Provenance obligatoire.
    if provenance is None:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=None,
            reason="Preuve de provenance absente.",
            action=action,
            human_approval=human_approval,
        )

    provenance_status = (
        provenance.status.value
        if hasattr(provenance.status, "value")
        else str(provenance.status)
    )

    if provenance.status != ProvenanceStatus.RESOLVED:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=f"Provenance non autorisable: {provenance_status}.",
            action=action,
            human_approval=human_approval,
        )

    resolved = (
        _normalize_path(provenance.resolved_path)
        if provenance.resolved_path
        else None
    )

    if resolved != path:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "La provenance résolue ne correspond pas "
                "au fichier d'évidence."
            ),
            action=action,
            human_approval=human_approval,
        )

    # 7. Action Dossier obligatoire et borné.
    if not action.action_id.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="ActionDossier sans action_id.",
            action=action,
            human_approval=human_approval,
        )

    if not action.action_type.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="ActionDossier sans action_type.",
            action=action,
            human_approval=human_approval,
        )

    if _normalize_path(action.target_path) != path:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "ActionDossier target_path ne correspond pas "
                "au fichier autorisé."
            ),
            action=action,
            human_approval=human_approval,
        )

    if not action.risk.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="ActionDossier sans niveau de risque.",
            action=action,
            human_approval=human_approval,
        )

    if not action.reversibility.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="ActionDossier sans reversibilité.",
            action=action,
            human_approval=human_approval,
        )

    # 8. Approbation humaine complète obligatoire.
    if not human_approval.approved:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="Validation humaine absente.",
            action=action,
            human_approval=human_approval,
        )

    if not human_approval.approver.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="Approbateur absent.",
            action=action,
            human_approval=human_approval,
        )

    if not human_approval.approved_at.strip():
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="Timestamp d'approbation absent.",
            action=action,
            human_approval=human_approval,
        )

    # 9. Niveau d'autorité explicite et connu.
    valid_levels = {level.value for level in AuthorityLevel}

    if human_approval.authority_level not in valid_levels:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason="Niveau d'autorité invalide.",
            action=action,
            human_approval=human_approval,
        )

    # 10. L'autorisation du Coder ne doit pas devenir une autorisation
    #     d'exécution critique par défaut.
    if human_approval.authority_level in {
        AuthorityLevel.L5_EXECUTE_ACTION.value,
        AuthorityLevel.L6_CRITICAL_ACTION.value,
    }:
        return _reject(
            path=path,
            target=target,
            evidence=evidence,
            provenance=provenance,
            reason=(
                "Le niveau L5/L6 ne peut pas être accordé par "
                "ce contrat Coder 5F.3.6."
            ),
            action=action,
            human_approval=human_approval,
        )

    base_target = _target_from_project(target)

    return CoderAuthorization(
        path=path,
        target=base_target,
        evidence_status=evidence_result.status,
        evidence_sha256=evidence.content_sha256,
        provenance_status=provenance_status,
        provenance_source_path=provenance.source_path,
        provenance_resolved_path=provenance.resolved_path,
        action=action,
        human_approval=human_approval,
        human_validation_required=True,
        status=AuthorizationStatus.AUTHORIZED.value,
        reason=(
            "Cible, evidence ACCEPTED, provenance, scope, action "
            "et validation humaine concordent."
        ),
    )




def _validate_evidence_integrity(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
) -> tuple[bool, str]:
    """
    D5.6-G — Lie cryptographiquement l'autorisation
    au contenu actuel du fichier evidence dans la cible.

    Fail closed :
    - chemin vide => BLOCK
    - chemin hors repository => BLOCK
    - fichier absent => BLOCK
    - lecture impossible => BLOCK
    - SHA absent => BLOCK
    - SHA différent => BLOCK
    """

    try:
        root = Path(target.git_root).resolve()

        requested = _normalize_path(requested_path)

        if not requested:
            return False, "Evidence path vide"

        candidate = (root / requested).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            return False, "Evidence hors du repository cible"

        if not candidate.is_file():
            return False, "Fichier evidence introuvable"

        content = candidate.read_text(
            encoding="utf-8"
        )

        current_sha256 = content_sha256(content)

        authorized_sha256 = str(
            authorization.evidence_sha256
        ).strip().lower()

        if not authorized_sha256:
            return False, "Evidence SHA-256 absent"

        if current_sha256.lower() != authorized_sha256:
            return (
                False,
                (
                    "Evidence SHA-256 mismatch: "
                    f"authorized={authorized_sha256} "
                    f"current={current_sha256}"
                ),
            )

        return (
            True,
            "Evidence SHA-256 conforme",
        )

    except (OSError, UnicodeError) as exc:
        return (
            False,
            f"Impossible de vérifier l'intégrité: {exc}",
        )



def validate_authorization(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
    allowed_paths: list[str],
) -> tuple[bool, str]:
    """
    Vérifie qu'une autorisation existante n'est pas réutilisée
    sur une autre cible ou un autre périmètre.
    """

    requested = _normalize_path(requested_path)

    allowed = {
        _normalize_path(path)
        for path in allowed_paths
    }

    if authorization.status != AuthorizationStatus.AUTHORIZED.value:
        return False, "authorization is not AUTHORIZED"

    # D5.6-G7 — Reason binding obligatoire.
    # Pour une autorisation AUTHORIZED, le motif doit être
    # exactement celui produit par authorize().
    canonical_authorized_reason = (
        "Cible, evidence ACCEPTED, provenance, scope, action et validation humaine concordent."
    )

    if authorization.reason != canonical_authorized_reason:
        return False, "authorization reason does not match canonical authorized reason"


    # D5.6-G — Integrity binding obligatoire.
    evidence_ok, evidence_reason = _validate_evidence_integrity(
        authorization,
        target,
        requested_path,
    )

    if not evidence_ok:
        return False, evidence_reason


    if not _same_target(authorization, target):
        return False, "authorization target identity mismatch"

    if authorization.path != requested:
        return False, "requested path differs from authorized path"

    if requested not in allowed:
        return False, "requested path outside authorized scope"

    if authorization.evidence_status != EvidenceStatus.ACCEPTED:
        return False, "authorization evidence is not ACCEPTED"

    # D5.6-G — Provenance binding obligatoire.
    if authorization.provenance_status != ProvenanceStatus.RESOLVED.value:
        return False, "authorization provenance is not RESOLVED"

    provenance_source = _normalize_path(
        authorization.provenance_source_path or ""
    )

    provenance_resolved = _normalize_path(
        authorization.provenance_resolved_path or ""
    )

    if not provenance_source:
        return False, "authorization provenance source is missing"

    if not provenance_resolved:
        return False, "authorization provenance resolved path is missing"

    if provenance_resolved != requested:
        return False, "authorization provenance resolved path differs from authorized path"


    if authorization.action.target_path != requested:
        return False, "action target differs from authorized path"

    if not authorization.human_validation_required:
        return False, "human validation invariant missing"

    approval = authorization.human_approval

    if not approval.approved:
        return False, "human approval is not approved"

    if not approval.approver.strip():
        return False, "approver missing"

    if not approval.approved_at.strip():
        return False, "approval timestamp missing"

    if approval.authority_level not in {
        level.value for level in AuthorityLevel
    }:
        return False, "invalid authority level"

    if approval.authority_level in {
        AuthorityLevel.L5_EXECUTE_ACTION.value,
        AuthorityLevel.L6_CRITICAL_ACTION.value,
    }:
        return False, "L5/L6 authority is not valid for 5F.3.6"

    return True, "authorization valid"


def authorization_to_dict(
    authorization: CoderAuthorization,
) -> dict:
    return {
        "path": authorization.path,
        "target": {
            "git_root": authorization.target.git_root,
            "head": authorization.target.head,
            "repository_fingerprint": (
                authorization.target.repository_fingerprint
            ),
        },
        "evidence_status": authorization.evidence_status,
        "evidence_sha256": authorization.evidence_sha256,
        "provenance_status": authorization.provenance_status,
        "provenance_source_path": authorization.provenance_source_path,
        "provenance_resolved_path": authorization.provenance_resolved_path,
        "action": {
            "action_id": authorization.action.action_id,
            "action_type": authorization.action.action_type,
            "target_path": authorization.action.target_path,
            "risk": authorization.action.risk,
            "reversibility": authorization.action.reversibility,
        },
        "human_approval": {
            "approved": authorization.human_approval.approved,
            "approver": authorization.human_approval.approver,
            "approved_at": authorization.human_approval.approved_at,
            "authority_level": (
                authorization.human_approval.authority_level
            ),
        },
        "human_validation_required": (
            authorization.human_validation_required
        ),
        "status": authorization.status,
        "reason": authorization.reason,
    }


# ==================================================================
# V0.4.1 — BINDING CRYPTOGRAPHIQUE DU DIFF APPROUVÉ
# ==================================================================
#
# Objectif : lier la décision humaine aux OCTETS EXACTS du patch approuvé,
# afin qu'aucune modification du diff après approbation ne puisse être
# appliquée avec la même autorisation.
#
# OCTETS CANONIQUES (définition explicite, sans transformation) :
#   Le patch réellement consommé par D5.9 est la chaîne `diff` produite par
#   code_adapter.generate_diff_git(...) en agent_loop §4.7, transmise TELLE
#   QUELLE à run_controlled_apply(..., diff, ...) en §4.9. D5.9 l'écrit via
#       open(fd, "w", encoding="utf-8", newline="")
#   (aucune traduction de fin de ligne) puis `git apply`.
#   => Les octets canoniques du binding sont EXACTEMENT `diff.encode("utf-8")`.
#   AUCUNE normalisation (CRLF/LF/BOM/réencodage) n'est appliquée ici : le
#   hash porte sur la chaîne telle qu'elle sera écrite et appliquée.
#
# Ce contrôle est STRICTEMENT ADDITIF et FAIL-CLOSED : il n'assouplit aucun
# garde-fou D5.8/D5.9 existant. D5.8 reste l'autorité unique ; ce module ne
# crée pas de seconde autorité, il ajoute une condition nécessaire.


# V0.4.2 — Le binding du diff est OBLIGATOIRE sur tout chemin d'application.
# Drapeau à True par défaut. SÉMANTIQUE FAIL-CLOSED : le mettre à False ne
# « désactive » pas le binding pour laisser passer un patch non lié ; au
# contraire, l'orchestrateur (agent_loop §4.8bis) BLOQUE l'application dès que
# ce drapeau n'est pas True. Autrement dit, aucune configuration ne peut
# aboutir à une application SANS binding vérifié. Il n'existe aucun autre
# chemin vers D5.9 que §4.9, lui-même précédé de ce contrôle.
REQUIRE_DIFF_BINDING = True


def canonical_diff_bytes(diff_text: str) -> bytes:
    """
    Représentation canonique, en OCTETS, du patch approuvé. Identique aux
    octets écrits par D5.9 (_git_apply, encoding utf-8, newline="") avant
    `git apply`. AUCUNE normalisation : pas de strip de BOM, pas de
    conversion CRLF/LF, pas de réencodage. Fail-closed sur entrée non-str.
    """
    if not isinstance(diff_text, str):
        raise TypeError("canonical_diff_bytes attend une chaîne (str)")
    return diff_text.encode("utf-8")


def diff_sha256(diff_text: str) -> str:
    """SHA-256 des octets canoniques du patch (hex minuscule)."""
    import hashlib
    return hashlib.sha256(canonical_diff_bytes(diff_text)).hexdigest()


def verify_diff_binding(
    human_approval: HumanApproval,
    diff_text: str,
    *,
    expected_proposal_id: str | None = None,
) -> tuple[bool, str]:
    """
    Vérifie, FAIL-CLOSED, que la décision humaine est liée AUX OCTETS EXACTS
    du `diff_text` qui sera consommé par D5.9.

    Règles :
      - approbation absente / non approuvée        -> REFUS ;
      - expected_diff_sha256 absent sur l'approbation -> REFUS (binding exigé
        dès lors que ce contrôle est invoqué : on ne devine pas un hash) ;
      - diff_text vide / non-str                   -> REFUS ;
      - diff_sha256(diff_text) != expected_diff_sha256 -> REFUS (un seul octet
        modifié change le hash) ;
      - si expected_proposal_id est fourni et diffère de approval.proposal_id
        -> REFUS (la proposition approuvée n'est pas celle présentée).

    Ne relâche AUCUN contrôle existant : à utiliser EN PLUS de authorize()/
    validate_authorization(). Ne lit aucun fichier, n'appelle pas D5.9.
    """
    if human_approval is None:
        return False, "binding: approbation absente"
    if human_approval.approved is not True:
        return False, "binding: approbation non accordée"
    if not isinstance(diff_text, str) or not diff_text.strip():
        return False, "binding: diff absent ou vide"

    expected = human_approval.expected_diff_sha256
    if not expected or not str(expected).strip():
        return False, (
            "binding: expected_diff_sha256 absent de l'approbation "
            "(aucune liaison au diff -> refus fail-closed)"
        )

    actual = diff_sha256(diff_text)
    if actual.lower() != str(expected).strip().lower():
        return False, (
            "binding: diff_sha256 mismatch — le patch diffère du diff approuvé "
            f"(approuvé={str(expected)[:16]} actuel={actual[:16]})"
        )

    if expected_proposal_id is not None:
        if (human_approval.proposal_id or "") != expected_proposal_id:
            return False, (
                "binding: proposal_id mismatch — la proposition approuvée "
                "n'est pas celle présentée (nouvelle décision humaine requise)"
            )

    return True, "binding: diff conforme à la décision humaine"


# ==================================================================
# V0.4.3 — LIAISON D'UNE APPROBATION HUMAINE À UNE PROPOSITION PRÉSENTÉE
# ==================================================================
#
# `bind_approval` matérialise l'étape « l'humain approuve LA proposition
# présentée » : à partir d'une HumanApproval RÉELLE (approved=True, décidée
# par un humain) et de la PROPOSITION effectivement montrée, il retourne une
# NOUVELLE HumanApproval portant proposal_id + expected_diff_sha256 issus de
# cette proposition. Il NE FABRIQUE JAMAIS d'approbation : si l'entrée n'est
# pas approuvée, elle est retournée telle quelle (restera refusée en aval).
#
# Ce helper NE contourne PAS verify_diff_binding : il ne fait que transporter,
# dans l'approbation, l'empreinte de la proposition que l'humain a vue. Le
# gate §4.8bis recalcule ensuite le hash des OCTETS EXACTS du diff réellement
# produit et le compare ; toute dérive -> BLOCK.

def bind_approval(human_approval: "HumanApproval", proposal) -> "HumanApproval":
    """
    Retourne une copie de `human_approval` liée à `proposal`
    (proposal_id + expected_diff_sha256). Exige une proposition portant un
    diff_sha256 et un proposal_id réels ; sinon lève ValueError (fail-closed,
    on ne lie pas à une proposition sans empreinte). Ne crée pas d'approbation.
    """
    import dataclasses
    pid = getattr(proposal, "proposal_id", None)
    dsha = getattr(proposal, "diff_sha256", None)
    if not pid or not dsha:
        raise ValueError(
            "bind_approval: la proposition n'a ni proposal_id ni diff_sha256 "
            "(aucun diff réel) — liaison impossible"
        )
    # V0.4.4-A : horodater une expiration explicite au MOMENT de la décision
    # (bind = l'humain approuve CETTE proposition). On respecte un expires_at
    # déjà fourni ; sinon on dérive approved_at (ou maintenant) + TTL. Ne
    # fabrique pas l'approbation : exige human_approval.approved=True en amont.
    import datetime
    new_expires = getattr(human_approval, "expires_at", None)
    if not new_expires:
        base = _parse_iso(getattr(human_approval, "approved_at", "")) or _now_utc()
        try:
            ttl = int(APPROVAL_TTL_SECONDS)
        except (TypeError, ValueError):
            ttl = 0
        if ttl > 0:
            new_expires = (base + datetime.timedelta(seconds=ttl)).isoformat()
    return dataclasses.replace(
        human_approval, proposal_id=pid, expected_diff_sha256=dsha,
        expires_at=new_expires,
    )


# ==================================================================
# V0.4.4-A — EXPIRATION (TTL) DES APPROBATIONS HUMAINES
# ==================================================================
#
# SOURCE DE TEMPS : horloge murale du système, via
# datetime.datetime.now(timezone) (timezone-aware, UTC pour les comparaisons).
# LIMITES CONNUES (documentées) :
#   - la fiabilité dépend de l'horloge du système ; un recul d'horloge peut
#     prolonger apparemment une validité, une avance peut la raccourcir ;
#   - pas de source de temps signée/monotone ici (hors périmètre V0.4.4-A) ;
#   - skew d'horloge entre la machine d'approbation et celle d'application :
#     une petite tolérance de futur (CLOCK_SKEW_TOLERANCE_SECONDS) est admise
#     pour approved_at, mais au-delà c'est une incohérence -> REFUS.
#
# DURÉE PAR DÉFAUT : prudente (15 min), documentée, configurable. On NE PEUT
# PAS désactiver silencieusement l'expiration : une TTL <= 0 ou non numérique
# est traitée comme une CONFIGURATION INVALIDE -> REFUS fail-closed (jamais
# « validité infinie »).
APPROVAL_TTL_SECONDS = 900          # 15 minutes, prudent et documenté
CLOCK_SKEW_TOLERANCE_SECONDS = 60   # tolérance de futur pour approved_at


def _parse_iso(ts: str):
    """Parse une date ISO 8601 en datetime timezone-aware (UTC si naïf).
    Retourne None si invalide/vide (fail-closed en aval)."""
    import datetime
    if not isinstance(ts, str) or not ts.strip():
        return None
    raw = ts.strip()
    # Python <3.11 n'accepte pas le 'Z' final : on le normalise en +00:00.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _now_utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)


def effective_expiry(human_approval: "HumanApproval"):
    """
    Détermine l'instant d'expiration effectif (datetime UTC) ou None si
    indéterminable. Priorité :
      1. expires_at explicite (ISO) s'il est fourni ET valide ;
      2. sinon approved_at + APPROVAL_TTL_SECONDS.
    Fail-closed : approved_at absent/invalide -> None (=> REFUS en aval).
    TTL de configuration invalide (<=0, non entier) -> None (=> REFUS).
    """
    if human_approval is None:
        return None
    # TTL de configuration : jamais de désactivation silencieuse.
    try:
        ttl = int(APPROVAL_TTL_SECONDS)
    except (TypeError, ValueError):
        return None
    if ttl <= 0:
        return None

    exp = getattr(human_approval, "expires_at", None)
    if exp:
        parsed = _parse_iso(exp)
        return parsed  # None si invalide -> REFUS en aval

    import datetime
    approved = _parse_iso(getattr(human_approval, "approved_at", ""))
    if approved is None:
        return None
    return approved + datetime.timedelta(seconds=ttl)


def verify_approval_freshness(
    human_approval: "HumanApproval",
    *,
    now=None,
) -> tuple[bool, str]:
    """
    Vérifie, FAIL-CLOSED, qu'une approbation liée n'est pas expirée, au
    DERNIER point de contrôle avant application.

    REFUS si :
      - approbation absente / non approuvée ;
      - approved_at absent, vide ou invalide ;
      - approved_at dans un futur incohérent (> tolérance de skew) ;
      - expires_at fourni mais invalide ;
      - instant d'expiration indéterminable (TTL config invalide) ;
      - now > expiration (expirée).

    `now` injectable pour les tests (sinon horloge système UTC). N'écrit rien.
    """
    import datetime
    if human_approval is None:
        return False, "ttl: approbation absente"
    if human_approval.approved is not True:
        return False, "ttl: approbation non accordée"

    now = now or _now_utc()
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    now = now.astimezone(datetime.timezone.utc)

    approved = _parse_iso(getattr(human_approval, "approved_at", ""))
    if approved is None:
        return False, "ttl: date d'approbation absente ou invalide"

    # Futur incohérent : une approbation « émise » après maintenant
    # (au-delà de la tolérance de skew) est suspecte -> REFUS.
    if approved > now + datetime.timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        return False, (
            "ttl: date d'approbation dans le futur (incohérence d'horloge)")

    exp_raw = getattr(human_approval, "expires_at", None)
    if exp_raw and _parse_iso(exp_raw) is None:
        return False, "ttl: expires_at invalide"

    expiry = effective_expiry(human_approval)
    if expiry is None:
        return False, (
            "ttl: expiration indéterminable (TTL de configuration invalide "
            "ou date absente) — refus fail-closed")

    if now > expiry:
        return False, (
            f"ttl: approbation expirée (expiration={expiry.isoformat()} "
            f"< maintenant={now.isoformat()}) — nouvelle décision requise")

    return True, f"ttl: approbation fraîche (expiration={expiry.isoformat()})"
