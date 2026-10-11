"""Calculs deterministes - format francais."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

DEVISE_SYMBOLES = {"EUR": "\u20ac", "USD": "$", "CHF": "CHF", "GBP": "\u00a3"}


def _d(v):
    return Decimal(str(v))


def _round2(v):
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_fr(montant, devise="EUR"):
    """1500.00 -> 1 500,00 EUR"""
    d = _round2(_d(montant))
    s = f"{d:,.2f}"
    s = s.replace(",", "\u00a0").replace(".", ",")
    symb = DEVISE_SYMBOLES.get(devise.upper(), devise)
    return f"{s}\u00a0{symb}"


def format_pct(v):
    d = _d(v)
    if d == d.to_integral_value():
        s = f"{int(d)}"
    else:
        s = f"{d:.2f}".replace(".", ",")
    return f"{s}\u00a0%"


def compute_totals(lignes, tva_pct_default=20.0, devise="EUR"):
    total_ht = Decimal("0")
    total_tva = Decimal("0")
    lignes_calc = []
    for l in lignes:
        qte = _d(l.get("quantite", 1))
        prix_ht = _d(l.get("prix_ht", 0))
        tva_pct = _d(l.get("tva_pct", tva_pct_default))
        ligne_ht = _round2(qte * prix_ht)
        ligne_tva = _round2(ligne_ht * tva_pct / Decimal("100"))
        total_ht += ligne_ht
        total_tva += ligne_tva
        lignes_calc.append({
            "description": l.get("description", ""),
            "quantite": str(qte),
            "prix_ht_fr": format_fr(prix_ht, devise),
            "tva_pct_fr": format_pct(tva_pct),
            "ligne_ht_fr": format_fr(ligne_ht, devise),
        })
    total_ht = _round2(total_ht)
    total_tva = _round2(total_tva)
    total_ttc = _round2(total_ht + total_tva)
    return {
        "lignes": lignes_calc,
        "total_ht_fr": format_fr(total_ht, devise),
        "total_tva_fr": format_fr(total_tva, devise),
        "total_ttc_fr": format_fr(total_ttc, devise),
        "total_ttc_raw": str(total_ttc),
    }
