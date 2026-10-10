"""
MemoLibDev — V0.2 : Tests du contrat d'états humains + front conversationnel
============================================================================

Prouve :
  - la traduction états RÉELS -> états HUMAINS est fidèle et déterministe ;
  - un état terminal NÉGATIF n'est JAMAIS présenté comme un succès ;
  - la progression est dérivée de l'état réel (jamais inventée/animée) ;
  - un état inconnu/absent est fail-safe (FAILED, pas un faux succès) ;
  - le front est NON AUTORITAIRE, supprimable, et n'ajoute ni route ni
    mécanisme d'autorisation ; le Core reste identique sans lui.

Déterministe. Aucun moteur, aucun git, aucun réseau, aucun apply.

Épreuves :
  H1  les 14 états humains existent avec une phrase
  H2  chaque état serveur réel mappe vers un état humain connu
  H3  terminal négatif => is_success False (invariant dur)
  H4  terminal de succès => is_success True (ANALYZED/COMPLETED)
  H5  état inconnu/None => FAILED (fail-safe, jamais faux succès)
  H6  progression déterministe + monotone (done<current<todo par index)
  H7  terminal négatif : étape atteinte jamais "done" (pas de faux succès)
  H8  COMPLETED : dernière étape "done" ; message = succès
  H9  AWAITING_APPROVAL : "Votre décision est nécessaire" + étape Décider
  W1  front : static_provider sert / et /index.html uniquement
  W2  front : routes JS = {/mission,/approve,/reject} (aucune autre)
  W3  front : le JS ne fabrique pas d'approbation (approved/authority_level)
  W4  front : aucun secret technique affiché par défaut (hors <details>)
  W5  front : Core identique sans front (make_handler défaut = None)
  W6  front : removabilité (serve_ui délègue à api_facade.serve)
  W7  front : miroir JS cohérent avec le contrat Python (états & mapping)
"""

from __future__ import annotations

import ast
import inspect
import os
import re

# Importer api_facade (indirectement via d'autres modules) déclenche une
# résolution de cible au niveau module de certains composants (comportement
# EXISTANT, hors périmètre V0.2). On fournit MEMOLIBDEV_TARGET en lecture
# seule, pointé sur le dépôt MemoLibDev lui-même, uniquement pour permettre
# l'import. Aucune écriture, aucune analyse réelle de cible.
os.environ.setdefault("MEMOLIBDEV_TARGET", os.path.dirname(__file__))

import human_states as hs
from human_states import (
    HUMAN_STATES, build_human_state_view, to_human_state,
    NEGATIVE_TERMINAL_STATES, SUCCESS_TERMINAL_STATES, PROGRESS_STEPS,
)
import conversation_ui
from conversation_ui import static_provider, _INDEX_HTML


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# Les 14 clés du contrat exigé.
_EXPECTED_HUMAN = [
    "UNDERSTANDING", "INSPECTING", "VERIFYING", "ANALYZING", "ANALYZED",
    "PROPOSING", "AWAITING_APPROVAL", "EXECUTING", "VERIFYING_RESULT",
    "COMPLETED", "REFUSED", "BLOCKED", "ROLLED_BACK", "FAILED",
]

# États serveur RÉELS (api_facade.MissionState + status moteur).
_REAL_SERVER_STATES = [
    "ANALYZING", "PROPOSAL_READY", "AWAITING_AUTHORIZATION", "AUTHORIZED",
    "EXECUTING", "VERIFYING", "COMPLETED", "REFUSED", "BLOCKED", "FAILED",
    "ROLLED_BACK", "QUESTION",
    "ANALYZED", "AWAIT_HUMAN", "APPLIED", "NO_PATCH_POSSIBLE", "OK", "ERROR",
]


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST V0.2 états humains + front conversationnel")
    print("=" * 72)

    # H1 — 14 états humains + phrase
    print("\n[H1] contrat des 14 états humains")
    for k in _EXPECTED_HUMAN:
        ok(f"H1 état {k} présent", k in HUMAN_STATES and bool(HUMAN_STATES[k]))
    ok("H1 pas d'état humain surnuméraire",
       set(HUMAN_STATES.keys()) == set(_EXPECTED_HUMAN),
       str(sorted(set(HUMAN_STATES) ^ set(_EXPECTED_HUMAN))))

    # H2 — chaque état serveur réel -> état humain connu
    print("\n[H2] mapping états serveur réels -> états humains connus")
    for s in _REAL_SERVER_STATES:
        v = build_human_state_view(s)
        ok(f"H2 {s} -> {v.human_state}",
           v.human_state in HUMAN_STATES, v.human_state)

    # H3 — terminal négatif => jamais un succès
    print("\n[H3] terminal négatif => is_success == False")
    for s in ("REFUSED", "BLOCKED", "FAILED", "ROLLED_BACK", "NO_PATCH_POSSIBLE",
              "ERROR"):
        v = build_human_state_view(s)
        ok(f"H3 {s} is_success False", v.is_success is False,
           f"human={v.human_state}")
        ok(f"H3 {s} is_negative True", v.is_negative is True)

    # H4 — terminal de succès => is_success True
    print("\n[H4] terminal de succès => is_success True")
    for s, human in (("ANALYZED", "ANALYZED"), ("PROPOSAL_READY", "ANALYZED"),
                     ("COMPLETED", "COMPLETED"), ("APPLIED", "COMPLETED")):
        v = build_human_state_view(s)
        ok(f"H4 {s} -> {human} succès", v.human_state == human and v.is_success is True)

    # H5 — inconnu/None -> FAILED (fail-safe)
    print("\n[H5] état inconnu/absent -> FAILED (jamais faux succès)")
    for bad in (None, "", "   ", "PWNED", "ADMIN", 123):
        v = build_human_state_view(bad if isinstance(bad, str) or bad is None else str(bad))
        ok(f"H5 {bad!r} -> FAILED", v.human_state == "FAILED", v.human_state)
        ok(f"H5 {bad!r} non succès", v.is_success is False)
    ok("H5 to_human_state(None) == FAILED", to_human_state(None) == "FAILED")

    # H6 — progression déterministe + ordonnée
    print("\n[H6] progression déterministe et cohérente")
    v1 = build_human_state_view("ANALYZING")
    v2 = build_human_state_view("ANALYZING")
    ok("H6 déterministe", v1.to_dict() == v2.to_dict())
    labels = [s.label for s in v1.progression]
    ok("H6 7 étapes dans l'ordre",
       labels == [l for _, l in PROGRESS_STEPS], str(labels))
    # Monotonie : une fois qu'on quitte "done", on ne revient pas à "done".
    seq = [s.status for s in v1.progression]
    done_prefix = True
    monotone = True
    for st in seq:
        if st == "done" and not done_prefix:
            monotone = False
        if st != "done":
            done_prefix = False
    ok("H6 statuts monotones (done* current? todo*)", monotone, str(seq))

    # H7 — terminal négatif : étape atteinte jamais "done"
    print("\n[H7] terminal négatif : aucune étape 'done' trompeuse")
    for s in ("BLOCKED", "REFUSED", "FAILED"):
        v = build_human_state_view(s)
        current = [st for st in v.progression if st.status == "current"]
        # L'étape d'arrêt est "current", pas "done" ; et aucune étape
        # postérieure n'est "done".
        ok(f"H7 {s} a une étape courante (arrêt)", len(current) == 1, str(current))
        # Vérifie qu'aucune étape "done" n'apparaît APRÈS la courante.
        idx_cur = next(i for i, st in enumerate(v.progression) if st.status == "current")
        after_done = any(st.status == "done" for st in v.progression[idx_cur + 1:])
        ok(f"H7 {s} aucune étape 'done' après l'arrêt", not after_done)

    # H8 — COMPLETED : dernière étape done + message succès
    print("\n[H8] COMPLETED : succès réel")
    v = build_human_state_view("COMPLETED")
    ok("H8 message = Terminé", v.message == "Terminé")
    ok("H8 is_success True", v.is_success is True)
    ok("H8 dernière étape done", v.progression[-1].status == "done")

    # H9 — AWAITING_APPROVAL
    print("\n[H9] AWAITING_APPROVAL")
    v = build_human_state_view("AWAITING_AUTHORIZATION")
    ok("H9 message décision", v.message == "Votre décision est nécessaire")
    ok("H9 non terminal", v.is_terminal is False)
    cur = [s.key for s in v.progression if s.status == "current"]
    ok("H9 étape courante = Décider", cur == ["DECIDER"], str(cur))

    # ---------------- Front conversationnel ----------------

    # W1 — static_provider
    print("\n[W1] front : static_provider")
    for p in ("/", "/index.html"):
        served = static_provider(p)
        ok(f"W1 {p} servi html", served is not None and served[0].startswith("text/html"))
    for p in ("/mission", "/approve", "/admin", "/secret"):
        ok(f"W1 {p} -> None", static_provider(p) is None)

    # W2 — routes appelées par le JS
    print("\n[W2] front : routes JS limitées")
    called = set(re.findall(r'callApi\(\s*"(/[a-zA-Z]+)"', _INDEX_HTML))
    ok("W2 routes = {/mission,/approve,/reject}",
       called == {"/mission", "/approve", "/reject"}, str(sorted(called)))

    # W3 — pas de fabrication d'autorité côté navigateur
    print("\n[W3] front : navigateur non autoritaire")
    ok("W3 pas de approved:true", "approved" not in _INDEX_HTML)
    ok("W3 pas de authority_level émis", "authority_level" not in _INDEX_HTML)
    ok("W3 pas de certificate", "certificate" not in _INDEX_HTML)
    approve_body = re.search(r'callApi\(\s*"/approve",\s*\{([^}]*)\}', _INDEX_HTML)
    ok("W3 /approve n'envoie que run_id+approver",
       approve_body is not None and "run_id" in approve_body.group(1)
       and "approver" in approve_body.group(1)
       and "diff" not in approve_body.group(1)
       and "sha" not in approve_body.group(1),
       approve_body.group(1) if approve_body else "introuvable")

    # W4 — aucun secret technique affiché par défaut (hors section <details>)
    print("\n[W4] front : technique masqué par défaut")
    before_details = _INDEX_HTML.split("<details", 1)[0].lower()
    for leak in ("d5.8", "d5.9", "sha256", "evidence_sha", "git apply",
                 "coder_authorization", "controlled_apply", "memolibdev_target"):
        ok(f"W4 pas de {leak!r} hors détails",
           leak not in before_details, f"présent avant <details>")
    ok("W4 section 'Voir les détails techniques' présente",
       "Voir les détails techniques" in _INDEX_HTML)
    ok("W4 détails techniques dans un élément <details> (masqué par défaut)",
       'el("details"' in _INDEX_HTML and "details.tech" in _INDEX_HTML)

    # W5 — Core identique sans front
    print("\n[W5] front : Core identique sans interface")
    from api_facade import make_handler
    sig = inspect.signature(make_handler)
    ok("W5 static_provider défaut = None",
       sig.parameters["static_provider"].default is None)
    api_src = inspect.getsource(make_handler)
    ok("W5 do_GET -> 404 sans static_provider",
       "static_provider is None" in api_src and "NOT_FOUND" in api_src)

    # W6 — removabilité
    print("\n[W6] front : removabilité / non-intrusivité")
    ui_src = inspect.getsource(conversation_ui)
    tree = ast.parse(ui_src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    ok("W6 pas de subprocess", "subprocess" not in imported, str(sorted(imported)))
    ok("W6 pas de socketserver propre", "socketserver" not in imported)
    ok("W6 serve_ui délègue à api_facade.serve", "from api_facade import serve" in ui_src)
    ok("W6 ne construit pas d'HumanApproval", "HumanApproval" not in ui_src)
    ok("W6 ne touche NI D5.8 NI D5.9",
       "d59_controlled_apply" not in imported and "coder_authorization" not in imported)

    # W7 — miroir JS cohérent avec le contrat Python
    print("\n[W7] front : miroir JS cohérent avec human_states")
    # Chaque clé d'état humain Python doit apparaître dans le JS.
    missing = [k for k in HUMAN_STATES if k not in _INDEX_HTML]
    ok("W7 toutes les clés humaines présentes dans le JS", missing == [], str(missing))
    # Les ensembles négatif/succès du JS reflètent le Python.
    for neg in NEGATIVE_TERMINAL_STATES:
        ok(f"W7 négatif {neg} dans le JS NEGATIVE", f'"{neg}"' in _INDEX_HTML)
    for suc in SUCCESS_TERMINAL_STATES:
        ok(f"W7 succès {suc} dans le JS SUCCESS", f'"{suc}"' in _INDEX_HTML)
    # Fail-safe JS présent : état inconnu -> FAILED.
    ok("W7 fail-safe JS -> FAILED",
       'return "FAILED"' in _INDEX_HTML and 'toHuman' in _INDEX_HTML)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT V0.2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
