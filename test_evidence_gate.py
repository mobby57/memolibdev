"""
MemoLibDev — Test Evidence Gate v1 (déterministe, fail-closed)
==============================================================
"""

from __future__ import annotations

from evidence_gate import (
    classify, InspectedFile, EvidenceResult,
    FACT, INFERENCE, HYPOTHESIS, UNKNOWN, ACCEPT, REVIEW, REJECT,
)


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


PROXY = InspectedFile(
    path="src/proxy.ts",
    content="export function handleAuth(){ return clerkMiddleware(); }\n",
    sha256="aaa", role="SOURCE")
LOGIN = InspectedFile(
    path="src/auth/login.ts",
    content="export const login = () => signInWithClerk();\n",
    sha256="bbb", role="SOURCE")
OTHER = InspectedFile(
    path="src/utils/date.ts",
    content="export function formatDate(d){ return d.toISOString(); }\n",
    sha256="ccc", role="SOURCE")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST Evidence Gate v1")
    print("=" * 72)

    # A — FACT démontré directement (fragment cité présent dans le fichier cité)
    r = classify('src/proxy.ts contient "clerkMiddleware"', [PROXY, LOGIN])
    ok("A_fact_direct", r.classification == FACT and r.verdict == ACCEPT,
       f"{r.classification}/{r.verdict}")
    ok("A_evidence", "src/proxy.ts" in r.evidence_used, str(r.evidence_used))

    # B — FACT prétendu sans preuve -> pas d'ACCEPT
    r = classify('src/proxy.ts contient "getStripeSession"', [PROXY, LOGIN])
    ok("B_fact_sans_preuve", r.verdict != ACCEPT, f"{r.classification}/{r.verdict}")
    ok("B_contradiction_ou_review", r.verdict in (REJECT, REVIEW), r.verdict)

    # C — contradiction explicite : fragment cité absent du fichier cité
    r = classify('src/auth/login.ts contient "logoutEverywhere"', [LOGIN])
    ok("C_reject", r.verdict == REJECT, f"{r.classification}/{r.verdict}")
    ok("C_contradictions", len(r.contradictions) >= 1, str(r.contradictions))

    # D — INFERENCE : éléments présents mais aucun fichier précis affirmé
    r = classify('le code utilise clerkMiddleware quelque part', [PROXY, LOGIN])
    ok("D_inference_review", r.verdict == REVIEW, f"{r.classification}/{r.verdict}")

    # E — HYPOTHESIS : claim formulé comme hypothèse
    r = classify('le bug vient probablement de clerkMiddleware dans src/proxy.ts',
                 [PROXY])
    ok("E_hypothesis_review", r.classification == HYPOTHESIS and r.verdict == REVIEW,
       f"{r.classification}/{r.verdict}")

    # F — contexte vide -> UNKNOWN/REVIEW
    r = classify('src/proxy.ts contient "clerkMiddleware"', [])
    ok("F_contexte_vide", r.classification == UNKNOWN and r.verdict == REVIEW,
       f"{r.classification}/{r.verdict}")

    # G — claim vide -> fail-closed
    r = classify('', [PROXY])
    ok("G_claim_vide", r.classification == UNKNOWN and r.verdict == REVIEW, r.verdict)
    r2 = classify(None, [PROXY])
    ok("G_claim_none", r2.verdict == REVIEW, r2.verdict)

    # H — plusieurs fichiers : preuve dans le bon fichier
    r = classify('src/auth/login.ts contient "signInWithClerk"',
                 [PROXY, LOGIN, OTHER])
    ok("H_multi_fichiers", r.verdict == ACCEPT and r.evidence_used == ("src/auth/login.ts",),
       f"{r.verdict} {r.evidence_used}")

    # I — preuve dans le MAUVAIS fichier : claim cite proxy mais le fragment
    # n'est que dans login -> pas d'ACCEPT (scopé au fichier cité).
    r = classify('src/proxy.ts contient "signInWithClerk"', [PROXY, LOGIN])
    ok("I_mauvais_fichier_pas_accept", r.verdict != ACCEPT,
       f"{r.classification}/{r.verdict}")

    # J — déterminisme
    a = classify('src/proxy.ts contient "clerkMiddleware"', [PROXY, LOGIN]).to_dict()
    b = classify('src/proxy.ts contient "clerkMiddleware"', [PROXY, LOGIN]).to_dict()
    ok("J_deterministe", a == b, "")

    # L — aucune modification externe : classify est pure (pas d'attribut d'effet)
    r = classify('src/proxy.ts contient "clerkMiddleware"', [PROXY])
    ok("L_pas_effet", not hasattr(r, "apply") and not hasattr(r, "commit"),
       "EvidenceResult ne porte aucun effet")
    ok("L_fail_closed_flag", r.fail_closed is True, "")

    # ---- Adversariaux ----
    print("\n[Adversariaux]")

    # Fichier contenant seulement un mot correspondant au claim (pas le fichier cité)
    noise = InspectedFile(path="docs/notes.md",
                          content="clerkMiddleware clerkMiddleware clerkMiddleware\n")
    r = classify('src/proxy.ts contient "clerkMiddleware"', [noise])
    ok("ADV_fichier_cite_absent", r.verdict == REVIEW,
       "fichier cité absent -> REVIEW, pas ACCEPT sur le bruit")

    # Chemin similaire mais mauvais fichier
    similar = InspectedFile(path="src/proxy.test.ts",
                            content="describe('proxy', () => {});\n")
    r = classify('src/proxy.ts contient "clerkMiddleware"', [similar])
    ok("ADV_chemin_similaire", r.verdict in (REVIEW, REJECT) and r.verdict != ACCEPT,
       f"{r.verdict}")

    # Claim très vague
    r = classify('corrige le problème', [PROXY, LOGIN])
    ok("ADV_vague", r.classification == UNKNOWN and r.verdict == REVIEW,
       f"{r.classification}/{r.verdict}")

    # Claim très précis mais sans preuve
    r = classify('src/proxy.ts contient "superSecretBackdoor42"', [PROXY])
    ok("ADV_precis_sans_preuve", r.verdict != ACCEPT, f"{r.verdict}")

    # Phrase 'LLM-like' affirmative sans guillemets ni fichier -> pas FACT
    r = classify("j'ai trouvé la cause du bug", [PROXY, LOGIN])
    ok("ADV_llm_phrase_pas_fact", r.classification != FACT, r.classification)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT Evidence Gate : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Déterministe, fail-closed, aucune autorité d'exécution.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
