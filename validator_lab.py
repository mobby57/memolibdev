from __future__ import annotations

import re


PATH_RE = re.compile(
    r"(?:src[\\/][A-Za-z0-9_.@\-\\/]+)"
)


def normalize_path(path: str) -> str:
    return path.replace("/", "\\").strip().strip("`'\".,;:()[]")


def extract_paths(text: str) -> list[str]:
    found = PATH_RE.findall(text or "")

    result = []

    for path in found:
        normalized = normalize_path(path)

        if normalized not in result:
            result.append(normalized)

    return result


def get_status(response: str) -> str:
    match = re.search(
        r"\bSTATUT\s*:\s*(CONFIRME|POSSIBLE|NON_PROBLEMATIQUE|INSUFFISANT)\b",
        response or "",
        re.IGNORECASE,
    )

    return match.group(1).upper() if match else ""


def has_anomaly_status(response: str) -> bool:
    return get_status(response) in {"CONFIRME", "POSSIBLE"}


def has_insufficient_status(response: str) -> bool:
    return get_status(response) in {"INSUFFISANT", "NON_PROBLEMATIQUE"}


def has_suspicion_language(response: str) -> bool:
    text = response.lower()

    patterns = [
        r"\bil semble que\b",
        r"\bil semblerait que\b",
        r"\bsemble indiquer\b",
        r"\bsemble montrer\b",
        r"\bpeut indiquer\b",
        r"\bpourrait indiquer\b",
        r"\bpotentiellement\b",
        r"\bprobablement\b",
        r"\bne vérifie pas correctement\b",
        r"\bne semble pas\b",
        r"\bincorrect(?:e|ement)?\b",
        r"\bproblématique\b",
        r"\bproblème potentiel\b",
        r"\brisque de\b",
        r"\bpeut poser problème\b",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def has_evidence_marker(response: str) -> bool:
    text = response.lower()

    markers = [
        "preuve",
        "ligne",
        "extrait",
        "code",
        "car",
        "parce que",
        "dans le fichier",
        "on voit",
        "montre que",
        "indique que",
    ]

    return any(marker in text for marker in markers)


def extract_section(
    response: str,
    section: str,
    next_sections: list[str],
) -> str:

    pattern = (
        rf"{re.escape(section)}\s*:\s*(.*?)"
        rf"(?=\n(?:{'|'.join(map(re.escape, next_sections))})\s*:|\Z)"
    )

    match = re.search(
        pattern,
        response or "",
        flags=re.IGNORECASE | re.DOTALL,
    )

    return match.group(1).strip() if match else ""


def has_concrete_evidence(response: str) -> bool:
    text = response.lower()

    patterns = [
        r"\bauth\s*\(",
        r"\bclerkmiddleware\b",
        r"\bcurrentuser\s*\(",
        r"\bverifyauth\s*\(",
        r"\bverifytoken\s*\(",
        r"\bauthorization\b",
        r"\bbearer\b",
        r"\bmatcher\b",
        r"\bpublicroutes?\b",
        r"\bprotectedroutes?\b",
        r"\boauthtokenservice\b",
        r"\bensurevalidtoken\b",
        r"\buser\.id\b",
        r"\bnextresponse\b",
        r"\b401\b",
        r"\b403\b",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def has_weak_cooccurrence_reasoning(response: str) -> bool:
    text = response.lower()

    patterns = [
        r"utilise également auth",
        r"utilisent auth",
        r"même fonction auth",
        r"plusieurs appels? à auth",
        r"double authentification",
        r"vérification double",
        r"les deux.*auth",
        r"deux.*auth\(",
        r"auth\(\).*auth\(",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def evidence_matches_claim(
    response: str,
    context: str,
) -> bool:

    evidence = extract_section(
        response,
        "PREUVE",
        ["RAISONNEMENT", "STATUT", "FICHIERS", "PROBLEME"],
    ).lower()

    if not evidence:
        return False

    context_lower = (context or "").lower()

    technical_tokens = [
        "auth(",
        "clerkmiddleware",
        "verifyauth(",
        "verifytoken(",
        "authorization",
        "bearer",
        "matcher",
        "publicroutes",
        "protectedroutes",
        "ensurevalidtoken",
        "oauth",
        "user.id",
        "nextresponse",
        "401",
        "403",
    ]

    mentioned = [
        token
        for token in technical_tokens
        if token in evidence
    ]

    if not mentioned:
        return False

    return any(token in context_lower for token in mentioned)


def evidence_is_claim_relevant(
    response: str,
) -> bool:

    problem = extract_section(
        response,
        "PROBLEME",
        ["PREUVE", "RAISONNEMENT", "STATUT", "FICHIERS"],
    ).lower()

    evidence = extract_section(
        response,
        "PREUVE",
        ["RAISONNEMENT", "STATUT", "FICHIERS", "PROBLEME"],
    ).lower()

    combined = problem + "\n" + evidence

    # --------------------------------------------------------
    # FAUX POSITIF : auth() + OAuth
    # --------------------------------------------------------

    auth_oauth_claim = (
        "oauth" in problem
        and (
            "auth()" in problem
            or "auth(" in problem
            or "authentifi" in problem
        )
    )

    if auth_oauth_claim:

        if (
            "auth(" in evidence
            and "oauth" not in evidence
            and "ensurevalidtoken" not in evidence
            and "token" not in evidence
            and "user.id" not in evidence
        ):
            return False

    # --------------------------------------------------------
    # FAUX POSITIF : deux auth()
    # --------------------------------------------------------

    if (
        "double authentification" in combined
        or "vérification double" in combined
    ):
        return False

    # --------------------------------------------------------
    # PREUVE HORS SUJET :
    #
    # problème = OAuth middleware
    # preuve = uniquement clerkMiddleware/matcher
    #
    # La preuve parle d'un autre mécanisme.
    # --------------------------------------------------------

    oauth_middleware_claim = (
        "middleware oauth" in problem
        or "middleware oauth" in problem.replace("-", " ")
        or (
            "oauth" in problem
            and "middleware" in problem
        )
    )

    if oauth_middleware_claim:

        proof_only_global_middleware = (
            "clerkmiddleware" in evidence
            and "matcher" in evidence
            and "auth(" not in evidence
            and "ensurevalidtoken" not in evidence
            and "oauth" not in evidence
            and "token" not in evidence
        )

        if proof_only_global_middleware:
            return False

    return True


def validate_claim(
    model_response: str,
    inspected_files: list[str],
    context: str,
) -> dict:

    response = model_response or ""

    normalized_inspected = {
        normalize_path(path)
        for path in inspected_files
        if path
    }

    cited_files = extract_paths(response)

    grounded_files = [
        path
        for path in cited_files
        if path in normalized_inspected
    ]

    unknown_files = [
        path
        for path in cited_files
        if path not in normalized_inspected
    ]

    anomaly_claim = has_anomaly_status(response)
    insufficient_status = has_insufficient_status(response)
    evidence_marker = has_evidence_marker(response)
    concrete_evidence = has_concrete_evidence(response)
    weak_reasoning = has_weak_cooccurrence_reasoning(response)
    suspicion_language = has_suspicion_language(response)

    evidence_grounded = evidence_matches_claim(
        response,
        context,
    )

    evidence_relevant = evidence_is_claim_relevant(
        response,
    )

    reasons: list[str] = []

    # --------------------------------------------------------
    # Fichier inconnu
    # --------------------------------------------------------

    if unknown_files:
        return {
            "verdict": "REJECT",
            "status": get_status(response),
            "cited_files": cited_files,
            "grounded_files": grounded_files,
            "unknown_files": unknown_files,
            "has_anomaly_claim": anomaly_claim,
            "has_evidence_marker": evidence_marker,
            "has_concrete_evidence": concrete_evidence,
            "evidence_grounded": evidence_grounded,
            "evidence_relevant": evidence_relevant,
            "weak_reasoning_detected": weak_reasoning,
            "suspicion_language_detected": suspicion_language,
            "reasons": [
                "Un fichier cité n'est pas présent parmi les fichiers inspectés."
            ],
        }

    # --------------------------------------------------------
    # Anomalie affirmée
    # --------------------------------------------------------

    if anomaly_claim:

        if not grounded_files:
            reasons.append(
                "Aucune preuve correctement ancrée dans un fichier inspecté."
            )

        if not evidence_marker:
            reasons.append(
                "Absence de marqueur de preuve."
            )

        if not concrete_evidence:
            reasons.append(
                "La preuve ne contient pas d'élément technique identifiable."
            )

        if not evidence_grounded:
            reasons.append(
                "Les éléments techniques de la preuve ne sont pas retrouvés dans le contexte."
            )

        if not evidence_relevant:
            reasons.append(
                "La preuve citée ne démontre pas le problème annoncé."
            )

        if weak_reasoning:
            reasons.append(
                "Le raisonnement repose sur une simple co-occurrence."
            )

        if reasons:
            return {
                "verdict": "REVIEW",
                "status": get_status(response),
                "cited_files": cited_files,
                "grounded_files": grounded_files,
                "unknown_files": unknown_files,
                "has_anomaly_claim": anomaly_claim,
                "has_evidence_marker": evidence_marker,
                "has_concrete_evidence": concrete_evidence,
                "evidence_grounded": evidence_grounded,
                "evidence_relevant": evidence_relevant,
                "weak_reasoning_detected": weak_reasoning,
                "suspicion_language_detected": suspicion_language,
                "reasons": reasons,
            }

        return {
            "verdict": "ACCEPTABLE",
            "status": get_status(response),
            "cited_files": cited_files,
            "grounded_files": grounded_files,
            "unknown_files": unknown_files,
            "has_anomaly_claim": anomaly_claim,
            "has_evidence_marker": evidence_marker,
            "has_concrete_evidence": concrete_evidence,
            "evidence_grounded": evidence_grounded,
            "evidence_relevant": evidence_relevant,
            "weak_reasoning_detected": weak_reasoning,
            "suspicion_language_detected": suspicion_language,
            "reasons": [
                "Anomalie accompagnée d'une preuve technique ancrée et pertinente."
            ],
        }

    # --------------------------------------------------------
    # INSUFFISANT + affirmation suspecte
    # --------------------------------------------------------

    if insufficient_status and suspicion_language:

        reasons.append(
            "Le modèle indique INSUFFISANT mais formule une affirmation technique suspecte."
        )

        if not evidence_grounded:
            reasons.append(
                "La preuve technique n'est pas suffisamment ancrée."
            )

        if not evidence_relevant:
            reasons.append(
                "La preuve ne permet pas de soutenir directement l'affirmation."
            )

        return {
            "verdict": "REVIEW",
            "status": get_status(response),
            "cited_files": cited_files,
            "grounded_files": grounded_files,
            "unknown_files": unknown_files,
            "has_anomaly_claim": anomaly_claim,
            "has_evidence_marker": evidence_marker,
            "has_concrete_evidence": concrete_evidence,
            "evidence_grounded": evidence_grounded,
            "evidence_relevant": evidence_relevant,
            "weak_reasoning_detected": weak_reasoning,
            "suspicion_language_detected": suspicion_language,
            "reasons": reasons,
        }

    # --------------------------------------------------------
    # AFFIRMATION FACTUELLE SANS PREUVE SUFFISANTE
    #
    # Une réponse peut ne pas déclarer d'anomalie tout en
    # formulant des affirmations techniques sur les fichiers.
    # Dans ce cas, l'absence de preuve suffisante doit conduire
    # à REVIEW, et non à ACCEPTABLE.
    # --------------------------------------------------------

    factual_claim_without_proof = (
        bool(cited_files)
        and (
            not concrete_evidence
            or not evidence_grounded
            or not evidence_relevant
        )
    )

    if factual_claim_without_proof:
        reasons.append(
            "La réponse formule des constats sur des fichiers inspectés "
            "sans preuve technique suffisamment ancrée et pertinente."
        )

        return {
            "verdict": "REVIEW",
            "status": get_status(response),
            "cited_files": cited_files,
            "grounded_files": grounded_files,
            "unknown_files": unknown_files,
            "has_anomaly_claim": anomaly_claim,
            "has_evidence_marker": evidence_marker,
            "has_concrete_evidence": concrete_evidence,
            "evidence_grounded": evidence_grounded,
            "evidence_relevant": evidence_relevant,
            "weak_reasoning_detected": weak_reasoning,
            "suspicion_language_detected": suspicion_language,
            "reasons": reasons,
        }

    return {
        "verdict": "ACCEPTABLE",
        "status": get_status(response),
        "cited_files": cited_files,
        "grounded_files": grounded_files,
        "unknown_files": unknown_files,
        "has_anomaly_claim": anomaly_claim,
        "has_evidence_marker": evidence_marker,
        "has_concrete_evidence": concrete_evidence,
        "evidence_grounded": evidence_grounded,
        "evidence_relevant": evidence_relevant,
        "weak_reasoning_detected": weak_reasoning,
        "suspicion_language_detected": suspicion_language,
        "reasons": [
            "Aucune violation évidente détectée."
        ],
    }


def run_tests() -> None:

    inspected = [
        r"src\middleware\auth.ts",
        r"src\lib\auth\clerk-token.ts",
        r"src\lib\oauth\middleware.ts",
        r"src\middleware.ts",
        r"src\lib\clerk-auth.ts",
        r"src\app\api\oauth\tokens\route.ts",
        r"src\app\api\oauth\authorize\route.ts",
        r"src\app\api\oauth\callback\route.ts",
    ]

    context = """
FICHIER : src\middleware\auth.ts
export async function authMiddleware()
const authResult = await verifyAuth()
return NextResponse.json(..., { status: 401 })

FICHIER : src\lib\auth\clerk-token.ts
const { userId } = await auth()

FICHIER : src\lib\oauth\middleware.ts
export function withOAuthToken(provider)
const { userId } = await auth()
return oauthTokenService.ensureValidToken(userId, provider)

FICHIER : src\middleware.ts
clerkMiddleware()
matcher

FICHIER : src\lib\clerk-auth.ts
auth()
currentUser()
Authorization
Bearer

FICHIER : src\app\api\oauth\tokens\route.ts
auth()
oauthTokenService

FICHIER : src\app\api\oauth\authorize\route.ts
OAuth
NextResponse

FICHIER : src\app\api\oauth\callback\route.ts
auth()
OAuth
callback
"""

    cases = [

        (
            "A — VRAIE NON_PROBLEMATIQUE",
            """
STATUT: NON_PROBLEMATIQUE

FICHIERS:
- src/middleware/auth.ts

PROBLEME:
Aucune anomalie démontrable.

PREUVE:
Le fichier utilise verifyAuth() et renvoie 401 lorsque
l'authentification échoue.

RAISONNEMENT:
Cela correspond à un contrôle d'authentification classique.
""",
            "ACCEPTABLE",
        ),

        (
            "B — FAUX POSITIF AUTH/OAUTH",
            """
STATUT: CONFIRME

FICHIERS:
- src/middleware/auth.ts
- src/lib/oauth/middleware.ts

PROBLEME:
Les deux fichiers utilisent auth(), donc Clerk et OAuth
sont en conflit.

PREUVE:
Les deux fichiers utilisent auth().

RAISONNEMENT:
Il s'agit donc d'une double authentification.
""",
            "REVIEW",
        ),

        (
            "C — PREUVE HORS SUJET",
            """
STATUT: CONFIRME

FICHIERS:
- src/middleware.ts
- src/lib/oauth/middleware.ts

PROBLEME:
Le middleware OAuth ne vérifie pas l'authentification.

PREUVE:
src/middleware.ts utilise clerkMiddleware() et un matcher.

RAISONNEMENT:
Le middleware OAuth est donc incorrect.
""",
            "REVIEW",
        ),

        (
            "D — VRAIE ANOMALIE STRUCTURELLE",
            """
STATUT: CONFIRME

FICHIERS:
- src/middleware.ts
- src/app/api/oauth/callback/route.ts

PROBLEME:
La route OAuth callback est déclarée publique alors que
le matcher du middleware protège explicitement cette route.

PREUVE:
Le middleware contient matcher pour les routes API et la route
callback est déclarée publique dans le code inspecté.

RAISONNEMENT:
Les deux règles s'appliquent à la même route et sont contradictoires.
""",
            "ACCEPTABLE",
        ),

        (
            "E — CONFIRME MAIS PREUVE ABSENTE",
            """
STATUT: CONFIRME

FICHIERS:
- src/middleware.ts

PROBLEME:
Le matcher protège une route qui doit être publique.

PREUVE:
La route /api/private/example est explicitement protégée.

RAISONNEMENT:
Cette contradiction est démontrée.
""",
            "REVIEW",
        ),

        (
            "F — FICHIER INVENTE",
            """
STATUT: CONFIRME

FICHIERS:
- src/middleware.ts
- src/app/api/oauth/secret-route.ts

PROBLEME:
La route est publique malgré le middleware.

PREUVE:
Le code de secret-route.ts expose la route publiquement.
""",
            "REJECT",
        ),
    ]

    print("=" * 70)
    print("VALIDATOR LAB — TEST 5D.1")
    print("=" * 70)

    all_passed = True

    for name, response, expected in cases:

        result = validate_claim(
            model_response=response,
            inspected_files=inspected,
            context=context,
        )

        verdict = result["verdict"]
        passed = verdict == expected

        if not passed:
            all_passed = False

        print()
        print(name)
        print(f"  ATTENDU : {expected}")
        print(f"  OBTENU  : {verdict}")
        print(f"  RESULTAT : {'PASS' if passed else 'FAIL'}")
        print(f"  evidence_grounded : {result['evidence_grounded']}")
        print(f"  evidence_relevant : {result['evidence_relevant']}")

        for reason in result["reasons"]:
            print(f"    - {reason}")

    print()
    print("=" * 70)

    if all_passed:
        print("TEST 5D.1 : PASS")
        print("Grounding + pertinence de preuve + faux positifs validés.")
    else:
        print("TEST 5D.1 : FAIL")
        print("Le Validator nécessite encore un ajustement.")


if __name__ == "__main__":
    run_tests()

