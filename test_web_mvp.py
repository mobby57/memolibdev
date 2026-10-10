"""
MemoLibDev — Test du front MVP (web_mvp) + non-intrusivité
==========================================================

Prouve que le front est une COUCHE PRODUIT supprimable, sans logique de
sécurité, et que le Core reste identique sans lui.

Épreuves :
  W1  static_provider sert "/" et "/index.html" (text/html)
  W2  static_provider ignore query/fragment (/?x=1, /#a) -> page
  W3  static_provider renvoie None pour toute autre route (=> 404 serveur)
  W4  CORE IDENTIQUE : make_handler SANS static_provider => GET -> 404,
      et le defaut est None (aucun GET servi sans front)
  W5  le HTML ne contient AUCUN secret technique (sha, diff, git, D5.8/D5.9,
      certificate, authorization, authority_level, run_id en dur)
  W6  le JS n'appelle QUE /mission, /approve, /reject (aucune autre route)
  W7  le JS ne fabrique PAS d'approbation : approved=true / authority_level
      ne sont jamais émis par le navigateur
  W8  robustesse déclarée : anti-double-submit (setBusy) + timeout client
      (AbortController) présents
  W9  removabilité : serve_mvp délègue à api_facade.serve (pas de serveur
      concurrent, pas de logique de sécurité dans web_mvp)

Aucun moteur gelé touché. Aucun apply/commit/push.
"""

from __future__ import annotations

import ast
import re

import web_mvp
from web_mvp import static_provider, _INDEX_HTML


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST front MVP (web_mvp)")
    print("=" * 72)

    # W1 — sert / et /index.html
    print("\n[W1] static_provider sert la page")
    for path in ("/", "/index.html"):
        served = static_provider(path)
        ok(f"W1 {path} servi", served is not None, str(served is None))
        if served is not None:
            ct, body = served
            ok(f"W1 {path} content-type html", ct.startswith("text/html"), ct)
            ok(f"W1 {path} octets non vides", isinstance(body, bytes) and len(body) > 0)

    # W2 — ignore query/fragment
    print("\n[W2] query/fragment ignorés")
    ok("W2 /?x=1 servi", static_provider("/?x=1") is not None)
    ok("W2 /#a servi", static_provider("/#a") is not None)
    ok("W2 /index.html?v=2 servi", static_provider("/index.html?v=2") is not None)

    # W3 — autres routes -> None
    print("\n[W3] routes inconnues -> None (404 serveur)")
    for path in ("/mission", "/approve", "/reject", "/admin", "/secret", "/..%2f"):
        ok(f"W3 {path} -> None", static_provider(path) is None, repr(static_provider(path)))

    # W4 — Core identique sans front
    print("\n[W4] Core identique sans front (make_handler défaut)")
    import inspect
    from api_facade import make_handler
    sig = inspect.signature(make_handler)
    ok("W4 static_provider par défaut = None",
       sig.parameters["static_provider"].default is None)
    # Analyse du source : sans static_provider, do_GET répond 404.
    src_api = inspect.getsource(make_handler)
    ok("W4 do_GET renvoie 404 si static_provider None",
       "static_provider is None" in src_api and "NOT_FOUND" in src_api)

    # W5 — aucun secret technique dans le HTML
    print("\n[W5] aucun secret technique dans le HTML")
    html_low = _INDEX_HTML.lower()
    forbidden = ["sha256", "evidence_sha", "git apply", "d5.8", "d5.9",
                 "certificate", "authorization", "authority_level",
                 "diff --git", "controlled_apply", "coder_authorization"]
    leaks = [w for w in forbidden if w in html_low]
    ok("W5 aucun terme technique sensible", leaks == [], f"leaks={leaks}")
    # "git" seul peut apparaître dans un mot anodin ? On vérifie l'absence
    # de la notion exposée à l'utilisateur.
    ok("W5 pas de 'run_id' affiché en dur comme label",
       "run_id :" not in html_low and "identifiant technique" not in html_low)

    # W6 — le JS n'appelle QUE /mission, /approve, /reject
    print("\n[W6] routes appelées par le JS")
    called = set(re.findall(r'callApi\(\s*"(/[a-zA-Z]+)"', _INDEX_HTML))
    ok("W6 routes = {/mission,/approve,/reject}",
       called == {"/mission", "/approve", "/reject"}, str(sorted(called)))

    # W7 — le JS ne fabrique pas d'approbation
    print("\n[W7] le navigateur ne fabrique pas d'autorité")
    ok("W7 pas de approved:true émis", "approved" not in _INDEX_HTML)
    ok("W7 pas de authority_level émis", "authority_level" not in _INDEX_HTML)
    ok("W7 pas de certificate émis", "certificate" not in _INDEX_HTML)
    # /approve n'envoie que run_id + approver (nom).
    approve_body = re.search(r'callApi\(\s*"/approve",\s*\{([^}]*)\}', _INDEX_HTML)
    ok("W7 /approve n'envoie que run_id+approver",
       approve_body is not None
       and "run_id" in approve_body.group(1)
       and "approver" in approve_body.group(1)
       and "diff" not in approve_body.group(1)
       and "path" not in approve_body.group(1),
       approve_body.group(1) if approve_body else "introuvable")

    # W8 — robustesse déclarée (anti-double-submit + timeout)
    print("\n[W8] robustesse : anti-double-submit + timeout client")
    ok("W8 verrou busy", "setBusy" in _INDEX_HTML and "if (busy) return" in _INDEX_HTML)
    ok("W8 timeout AbortController",
       "AbortController" in _INDEX_HTML and "CLIENT_TIMEOUT_MS" in _INDEX_HTML)
    ok("W8 message de timeout lisible", "trop de temps" in _INDEX_HTML.lower())
    ok("W8 aperçu avant approbation (can_approve pilote l'UI)",
       "data.can_approve" in _INDEX_HTML)
    ok("W8 avertissement d'effet",
       "modifiera votre projet" in _INDEX_HTML)
    ok("W8 boutons Refuser et Autoriser",
       "Refuser" in _INDEX_HTML and "Autoriser" in _INDEX_HTML)

    # W9 — removabilité : web_mvp délègue, ne crée pas de 2e serveur ni de
    #      logique de sécurité.
    print("\n[W9] removabilité / non-intrusivité")
    src = inspect.getsource(web_mvp)
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    ok("W9 pas de subprocess", "subprocess" not in imported, str(sorted(imported)))
    ok("W9 pas de socket/httpserver propre", "socketserver" not in imported)
    ok("W9 serve_mvp délègue à api_facade.serve", "from api_facade import serve" in src)
    # Aucune construction d'autorisation / HumanApproval côté front serveur.
    ok("W9 web_mvp ne construit pas d'HumanApproval",
       "HumanApproval" not in src)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT FRONT MVP : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
