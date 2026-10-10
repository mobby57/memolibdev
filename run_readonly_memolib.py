"""
MemoLibDev — Run READ-ONLY sur MemoLib réel
============================================

Premier contact avec le VRAI dépôt MemoLib (via MEMOLIBDEV_TARGET).
STRICTEMENT lecture seule : mission -> contexte -> Ollama -> proposition
-> diff candidat -> RAPPORT -> STOP.

GARANTIE D'INNOCUITÉ (par construction) :
  - ce script N'IMPORTE PAS et N'APPELLE JAMAIS run_controlled_apply (D5.9) ;
  - il s'arrête APRÈS la proposition (derive_intent + diff candidat) ;
  - aucune écriture disque, aucun git mutant, aucun commit/push ;
  - il CAPTURE HEAD + porcelain de la cible AVANT et APRÈS, et prouve
    qu'ils sont identiques.

Répond à la question : la chaîne fonctionne-t-elle face au vrai dépôt
(complexité réelle) et non seulement au sandbox ?
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from project_target import resolve_target, ProjectTargetError
from context.context_builder import build_mission_context, is_stale
from llm.llm_planner import derive_intent
from llm.ollama_provider import OllamaProvider
import code_adapter
from file_target import resolve_file_target, FileTargetError


MODEL = "qwen2.5-coder:1.5b-base"

# Mission read-only volontairement SIMPLE et SANS APPLY. On veut une
# proposition, pas une transformation appliquée.
MISSION = "propose une amélioration mineure et réversible d'un fichier de code"


def _safe(s: str) -> str:
    """Rend une chaîne imprimable sur une console à encodage limité
    (Windows cp1252) sans planter : les caractères non encodables sont
    remplacés. Affichage uniquement — n'altère aucune donnée du dépôt."""
    enc = (sys.stdout.encoding or "utf-8")
    try:
        return s.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        return s.encode("ascii", errors="replace").decode("ascii")


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def snapshot(root: Path) -> dict:
    return {
        "head": git(root, "rev-parse", "HEAD"),
        "porcelain": git(root, "status", "--porcelain"),
        "commit_count": git(root, "rev-list", "--count", "HEAD"),
        "remotes": git(root, "remote"),
    }


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — RUN READ-ONLY SUR MEMOLIB RÉEL")
    print("=" * 72)

    # 1. Résolution de la cible (MEMOLIBDEV_TARGET, pas de fallback).
    try:
        target = resolve_target()
    except ProjectTargetError as e:
        print(f"[STOP] Cible non résolue : {e}")
        return 2
    root = target.git_root
    print(f"Cible     : {root}")
    print(f"Branche   : {target.branch}")
    print(f"HEAD      : {target.head}")
    print(f"Empreinte : {target.fingerprint}")

    # 2. Snapshot AVANT (preuve d'innocuité).
    before = snapshot(root)
    print(f"\n[AVANT] HEAD={before['head'][:12]} "
          f"commits={before['commit_count']} "
          f"working_tree={'propre' if not before['porcelain'] else 'MODIFIÉ'}")

    # 3. Vérifier qu'Ollama est dispo (sinon STOP propre).
    provider = OllamaProvider(model=MODEL, http_timeout=180.0)
    if not provider.available:
        print(f"[STOP] Ollama/modèle {MODEL} indisponible.")
        return 0

    # 4. CONTEXTE (lecture seule, bornée au git_root).
    print("\n[CONTEXT] Construction du contexte (lecture seule)...")
    ctx = build_mission_context("RO-MEMOLIB-001", MISSION, target,
                                max_files=8, max_context_chars=6000)
    print(f"  fichiers pertinents : {len(ctx.relevant_files)}")
    for rf in ctx.relevant_files[:8]:
        print(f"    - {rf.path} (score={rf.score}, kind={rf.kind}, "
              f"text_sha={rf.version.text_sha256[:12]})")
    fresh = is_stale(ctx, target)
    print(f"  fraîcheur : {fresh.status}")

    if not ctx.relevant_files:
        print("[STOP] Aucun fichier pertinent — rien à proposer. (read-only)")
        _prove(before, snapshot(root))
        return 0

    # 5. PROPOSITION via Ollama (lecture seule) + timeout R4.
    print("\n[PROPOSAL] Dérivation d'une proposition via Ollama (timeout R4)...")
    planner = derive_intent(ctx, provider, timeout_s=200.0)
    print(f"  statut   : {planner.status}")
    print(f"  raison   : {planner.reason}")

    if planner.ok:
        print(f"  cible    : {planner.target_path}")
        print(f"  intent   : {_safe(planner.intent[:120])}")
        # 6. DIFF CANDIDAT (en mémoire, JAMAIS appliqué).
        try:
            ft = resolve_file_target(planner.target_path, target)
            content = code_adapter.read(ft)
            cplan = code_adapter.plan(content, planner.intent, ft.path)
            new_content = code_adapter.modify(content, cplan)
            valid, vreason = code_adapter.validate(content, new_content)
            print(f"  validate : {valid} ({vreason})")
            diff = code_adapter.generate_diff_git(root, ft.path, new_content)
            print("\n[DIFF CANDIDAT] (NON appliqué, affichage seulement)")
            print("-" * 72)
            for line in diff.splitlines()[:40]:
                print(_safe(line))
            print("-" * 72)
        except (FileTargetError, code_adapter.CodeAdapterError) as e:
            print(f"  [note] proposition non matérialisable en diff : {_safe(str(e))}")
    else:
        print("  -> BLOCK (fail-closed) : aucune proposition exploitable. "
              "C'est un résultat valide, pas une erreur.")

    # 7. STOP avant tout apply + preuves d'innocuité.
    print("\n[STOP] Aucun apply. run_controlled_apply (D5.9) JAMAIS appelé.")
    after = snapshot(root)
    _prove(before, after)
    return 0


def _prove(before: dict, after: dict) -> None:
    print("\n" + "=" * 72)
    print("PREUVES D'INNOCUITÉ (cible réelle)")
    print("=" * 72)
    checks = [
        ("HEAD inchangé", before["head"] == after["head"],
         f"{before['head'][:12]} == {after['head'][:12]}"),
        ("working tree inchangé", before["porcelain"] == after["porcelain"],
         f"avant={before['porcelain']!r} après={after['porcelain']!r}"),
        ("aucun nouveau commit",
         before["commit_count"] == after["commit_count"],
         f"{before['commit_count']} == {after['commit_count']}"),
        ("remotes inchangés", before["remotes"] == after["remotes"], ""),
    ]
    all_ok = True
    for name, cond, detail in checks:
        all_ok = all_ok and cond
        print(f"  [{'OK' if cond else 'ÉCHEC'}] {name}" + (f" :: {detail}" if detail else ""))
    print("=" * 72)
    print("VERDICT :", "READ-ONLY CONFIRMÉ" if all_ok else "ANOMALIE — VÉRIFIER")
    print("=" * 72)


if __name__ == "__main__":
    raise SystemExit(main())
