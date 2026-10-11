#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_doc.py - Genere un document en demandant le contexte d'abord.

Usage :
    python create_doc.py --type facture
    python create_doc.py --type facture --prefill "facture pour Dupont, 3 jours a 500"
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from document_engine.dialogue import collecter_donnees, afficher_resume, confirmer
from document_engine.fields import load_fields
from document_engine.calculator import compute_totals
from document_engine import render_template
from document_engine.renderers.pdf import render_pdf


TYPES_SUPPORTES = ("facture", "devis", "compte-rendu", "attestation", "rapport")


def prefill_depuis_texte(texte: str, template: str) -> dict:
    """Extrait des donnees simples d'un texte libre (regex basique)."""
    import re
    data = {}
    # Chercher "pour X" -> client.nom
    m = re.search(r"pour\s+(?:M(?:r|me|me|onsieur|adame)?\.?\s+)?([A-Z][\w\s'-]+)", texte)
    if m and template in ("facture", "devis"):
        data["client"] = {"nom": m.group(1).strip()}

    # Chercher "N x M EUR" ou "N jours a M"
    m = re.search(r"(\d+)\s*(?:jours?|x|unites?)\s*(?:a|@|\*)?\s*(\d+(?:[.,]\d+)?)\s*(?:EUR|euros?|EUR)?", texte)
    if m:
        data["lignes"] = [{
            "description": "Prestation",
            "quantite": int(m.group(1)),
            "prix_ht": float(m.group(2).replace(",", ".")),
            "tva_pct": "20",
        }]
    return data


def main():
    ap = argparse.ArgumentParser(description="Genere un document avec dialogue prealable")
    ap.add_argument("--type", required=True, choices=TYPES_SUPPORTES,
                    help="Type de document")
    ap.add_argument("--prefill", default="",
                    help="Texte libre pour pre-remplir des champs")
    ap.add_argument("--out", default=None,
                    help="Chemin de sortie (defaut : dist/<type>_<timestamp>.pdf)")
    args = ap.parse_args()

    template_dir = ROOT / "templates" / args.type
    if not template_dir.is_dir():
        print(f"[ERREUR] Template introuvable : {template_dir}")
        return 2

    print()
    print("=" * 60)
    print(f" NOUVEAU DOCUMENT : {args.type.upper()}")
    print("=" * 60)
    print(f" Template : {template_dir.relative_to(ROOT)}")

    # Pre-remplissage eventuel
    data_initial = {}
    if args.prefill:
        data_initial = prefill_depuis_texte(args.prefill, args.type)
        if data_initial:
            print(f" Pre-remplissage : {len(data_initial)} champ(s) extrait(s) du texte")

    try:
        data = collecter_donnees(template_dir, data_initial)
    except KeyboardInterrupt:
        print("\n[ANNULE]")
        return 130

    fields = load_fields(template_dir)
    resume_ok = afficher_resume(data, fields)
    if not resume_ok:
        print()
        print("[REFUS] Impossible de generer : champs obligatoires manquants.")
        print("        Le document n'a pas ete cree.")
        return 3

    if not confirmer():
        print("[ANNULE]")
        return 0

    # Generation
    print()
    print("Generation en cours...")
    html = render_template(template_dir, data)

    if args.out:
        out = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = ROOT / "dist" / f"{args.type}_{ts}.pdf"

    out.parent.mkdir(parents=True, exist_ok=True)
    pdf = render_pdf(html, output_path=out)
    print(f"[OK] PDF : {out} ({len(pdf)} octets)")
    print()

    import os
    os.startfile(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
