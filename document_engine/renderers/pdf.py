"""Rendu PDF via xhtml2pdf."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

try:
    from xhtml2pdf import pisa
except ImportError:
    raise ImportError("pip install xhtml2pdf")


class PDFError(RuntimeError):
    pass


def render_pdf(html: str, output_path: Path = None) -> bytes:
    """Convertit du HTML en PDF. Retourne les bytes, ecrit si output_path."""
    buf = BytesIO()
    html_bytes = html.encode("utf-8")
    result = pisa.CreatePDF(html_bytes, dest=buf, encoding="utf-8")
    if result.err:
        raise PDFError(f"xhtml2pdf : {result.err} erreur(s)")
    pdf_bytes = buf.getvalue()
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
    return pdf_bytes
