"""Rendu Jinja2 + QR paiement + format FR."""
from __future__ import annotations
import base64, io
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from .calculator import compute_totals
from .config_loader import load_config


def _gen_qr(data):
    try:
        import qrcode
    except ImportError:
        return ""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _build_qr_payload(tpl, societe, numero, devise, total_ttc):
    return (tpl
            .replace("{bic}", societe.get("bic", ""))
            .replace("{iban}", societe.get("iban", ""))
            .replace("{nom}", societe.get("nom", ""))
            .replace("{numero}", numero)
            .replace("{devise}", devise)
            .replace("{total_ttc}", total_ttc))


def render_template(template_dir, data):
    template_dir = Path(template_dir)
    cfg = load_config(template_dir)
    tva_default = cfg.get("tva", {}).get("taux_defaut", 20.0)
    devise = cfg.get("tva", {}).get("devise", "EUR")
    totals = compute_totals(data.get("lignes", []), tva_default, devise)

    date_emission = data.get("date") or datetime.now().strftime("%d/%m/%Y")
    date_echeance = data.get("date_echeance") or ""
    date_prestation = data.get("date_prestation") or date_emission
    numero = data.get("numero") or _gen_numero(cfg, data)

    qr_uri = ""
    pay = cfg.get("paiement", {})
    societe = cfg["societe"]
    if pay.get("qr_code") and societe.get("iban"):
        try:
            payload = _build_qr_payload(
                pay.get("qr_data_template", ""),
                societe, numero, devise, totals["total_ttc_raw"],
            )
            qr_uri = _gen_qr(payload)
        except Exception:
            pass

    # 1) Tous les champs du data d'entree (destinataire, signataire, corps, etc.)
    ctx = dict(data)

    # 2) Superposer les champs calcules / configurables (priorite haute)
    ctx.update({
        "societe": societe,
        "mentions": cfg["mentions"],
        "devise": devise,
        "numero": numero,
        "date": date_emission,
        "date_echeance": date_echeance,
        "date_prestation": date_prestation,
        "lignes": totals["lignes"],
        "total_ht": totals["total_ht_fr"],
        "total_tva": totals["total_tva_fr"],
        "total_ttc": totals["total_ttc_fr"],
        "tva_pct": f"{tva_default:.0f}",
        "qr_code_data_uri": qr_uri,
        "css": (template_dir / "style.css").read_text(encoding="utf-8"),
    })

    env = Environment(loader=FileSystemLoader(str(template_dir)),
                      autoescape=select_autoescape(["html"]))
    return env.get_template("template.html").render(**ctx)


def _gen_numero(cfg, data):
    n = cfg.get("numerotation", {})
    p = n.get("prefixe", "FA")
    a = datetime.now().year
    s = data.get("numero_sequence", 1)
    return f"{p}-{a}-{s:04d}"
