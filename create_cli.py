#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI separe pour le flux CREATE.
Ne touche PAS memolibdev_cli.py.
Usage :
  python create_cli.py --project <path> --mission "Genere une facture..." --model <model> [--approve]
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from create_parser import parse_create_intent, CreateParseError
from create_target import resolve_create_target, CreateTargetError
from create_apply import apply_create
from create_authorization import (
    build_create_approval, verify_create_approval,
    CreateAuthorizationError,
)

DEFAULT_MODEL = "memolibdev-qwen7b-16k:latest"


def build_create_prompt(mission: str, git_root: str) -> str:
    """Prompt strict pour generer un CREATE en JSON."""
    return (
        "Tu es un assistant qui cree UN SEUL fichier.\n"
        "Reponds EXCLUSIVEMENT par un objet JSON sur UNE SEULE LIGNE.\n"
        "Format STRICT :\n"
        '{"action":"CREATE","path":"<chemin_relatif>","format":"<fmt>","content":"<contenu>"}\n'
        "\n"
        "Regles :\n"
        "- path : chemin RELATIF, extension autorisee (md, txt, json, csv, html, pdf, docx, xlsx, py)\n"
        "- format : md | txt | json | csv | html | pdf | docx | xlsx\n"
        "- content : contenu COMPLET du fichier (echappe pour JSON)\n"
        "- UNE SEULE LIGNE, RIEN D\'AUTRE (pas de markdown, pas d\'explication)\n"
        "\n"
        "Exemple VALIDE :\n"
        '{"action":"CREATE","path":"rapport.md","format":"md","content":"# Rapport\\n\\nContenu."}\n'
        "\n"
        f"Mission : {mission}\n"
        f"Projet : {git_root}\n"
        "\n"
        "Reponse (UNE SEULE LIGNE JSON) :"
    )


def call_ollama(prompt: str, model: str, base_url: str = "http://localhost:11434",
                timeout: float = 300.0) -> str:
    """Appelle Ollama et retourne la reponse brute."""
    import urllib.request
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.0},
    }
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data.get("response", "")


def extract_json_line(text: str) -> str:
    """Extrait la premiere ligne qui ressemble a un JSON CREATE."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and "CREATE" in line:
            return line
    return ""


def main():
    ap = argparse.ArgumentParser(prog="create_cli")
    ap.add_argument("--project", required=True, help="Racine du depot (git_root).")
    ap.add_argument("--mission", required=True, help="Mission en francais.")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--approve", action="store_true",
                    help="Approuve automatiquement (pour tests).")
    ap.add_argument("--approver", default="cli_user")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    git_root = Path(args.project).resolve()
    if not (git_root / ".git").is_dir():
        print(f"[ERREUR] Pas un depot Git : {git_root}", file=sys.stderr)
        return 2

    print("=" * 60)
    print(" MemoLibDev CREATE")
    print(f" Projet : {git_root}")
    print(f" Modele : {args.model}")
    print("=" * 60)

    # 1. Prompt
    prompt = build_create_prompt(args.mission, str(git_root))

    # 2. Appel Ollama
    print("\n[1] Appel Ollama...")
    try:
        raw = call_ollama(prompt, args.model, timeout=args.timeout)
    except Exception as e:
        print(f"[ERREUR] Ollama : {e}", file=sys.stderr)
        return 3

    print(f"[OK] Reponse recue ({len(raw)} caracteres)")

    # 3. Extraction JSON
    print("\n[2] Parsing JSON...")
    line = extract_json_line(raw)
    if not line:
        print("[ERREUR] Aucun JSON CREATE dans la reponse.", file=sys.stderr)
        print(f"Reponse brute : {raw[:500]}", file=sys.stderr)
        return 4

    try:
        intent = parse_create_intent(line)
    except CreateParseError as e:
        print(f"[ERREUR] Parse : {e}", file=sys.stderr)
        return 4
    print(f"[OK] path={intent.path}  format={intent.format}")

    # 4. Resolution cible
    print("\n[3] Validation de la cible...")
    try:
        target = resolve_create_target(git_root, intent.path)
    except CreateTargetError as e:
        print(f"[ERREUR] Cible : {e}", file=sys.stderr)
        return 5
    print(f"[OK] Cible : {target.abs_path}")

    # 5. Preview
    print("\n" + "=" * 60)
    print(" CONTENU PROPOSE")
    print("=" * 60)
    preview = intent.content[:2000]
    print(preview)
    if len(intent.content) > 2000:
        print(f"... [tronque, {len(intent.content)} caracteres au total]")
    print("=" * 60)

    # 6. Approbation
    if not args.approve:
        try:
            ans = input("\nApprouver la creation ? (oui/non) > ").strip().lower()
        except EOFError:
            ans = "non"
        if ans not in ("oui", "o", "yes", "y"):
            print("[REFUSE] Aucune modification.")
            return 0

    # 7. Build approval
    try:
        approval = build_create_approval(
            approver=args.approver,
            target_path=target.rel_path,
            content=intent.content,
        )
        verify_create_approval(approval, target.rel_path, intent.content)
    except CreateAuthorizationError as e:
        print(f"[ERREUR] Autorisation : {e}", file=sys.stderr)
        return 6

    # 8. Apply avec verify
    def verify_file(p: Path):
        if not p.is_file():
            return (False, "fichier absent")
        content = p.read_text(encoding="utf-8")
        if not content.strip():
            return (False, "fichier vide")
        return (True, "ok")

    print("\n[4] Application...")
    result = apply_create(target, intent.content, verify_file)

    print("\n" + "-" * 60)
    print(f"STATUT : {result.status}")
    print(f"Fichier : {result.path}")
    if result.sha256:
        print(f"SHA256  : {result.sha256[:32]}...")
    print(f"Rollback: {result.rolled_back}")
    if result.reason:
        print(f"Raison  : {result.reason}")
    print("-" * 60)

    return 0 if result.status == "APPLIED" else 1


if __name__ == "__main__":
    sys.exit(main())
