"""Rendu XLSX pro - planning projet avec barres natives et protection."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from io import BytesIO

try:
    from openpyxl import Workbook
    from openpyxl.styles import (
        Font, PatternFill, Alignment, Border, Side, Protection,
    )
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import DataBarRule
    from openpyxl.worksheet.datavalidation import DataValidation
except ImportError:
    raise ImportError("pip install openpyxl")


COLOR_HEADER = "0F172A"
COLOR_ACCENT = "2563EB"
COLOR_OK = "DCFCE7"
COLOR_WARN = "FEF3C7"
COLOR_ERR = "FEE2E2"
COLOR_INFO = "DBEAFE"
COLOR_GRAY = "F8FAFC"

STATUT_STYLES = {
    "Termine": COLOR_OK,
    "En cours": COLOR_INFO,
    "En retard": COLOR_ERR,
    "A faire": COLOR_GRAY,
    "Bloque": COLOR_WARN,
}

STATUTS_VALIDES = ["Termine", "En cours", "En retard", "A faire", "Bloque"]


def _thin_border():
    side = Side(style="thin", color="E2E8F0")
    return Border(left=side, right=side, top=side, bottom=side)


def _parse_date(s):
    if isinstance(s, datetime):
        return s
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def render_planning_xlsx(config: dict, data: dict, output_path: Path = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Planning"

    societe = config.get("societe", {})
    projet = data.get("projet", "Planning de projet")

    # Titre
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = societe.get("nom", "")
    c.font = Font(size=11, color="64748B", bold=True)
    ws.row_dimensions[1].height = 20

    ws.merge_cells("A2:H2")
    c = ws["A2"]
    c.value = projet
    c.font = Font(size=18, color=COLOR_HEADER, bold=True)
    ws.row_dimensions[2].height = 32

    ws.merge_cells("A3:H3")
    c = ws["A3"]
    date_rapport = data.get("date", datetime.now().strftime("%d/%m/%Y"))
    c.value = f"Genere le {date_rapport} | Chef de projet : {data.get('chef_projet', '')}"
    c.font = Font(size=10, color="64748B", italic=True)
    ws.row_dimensions[3].height = 20

    ws.row_dimensions[4].height = 8

    # Headers
    headers = ["TACHE", "RESPONSABLE", "DEBUT", "FIN", "DUREE (j)", "AVANCEMENT", "STATUT", "PROGRESSION"]
    hr = 5
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=hr, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=COLOR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _thin_border()
        cell.protection = Protection(locked=True)
    ws.row_dimensions[hr].height = 24

    # Lignes
    taches = data.get("taches", [])
    row = hr + 1
    first_data_row = row

    for t in taches:
        debut = _parse_date(t.get("debut"))
        fin = _parse_date(t.get("fin"))
        duree = (fin - debut).days if (debut and fin) else 0
        avancement = int(t.get("avancement", 0))
        statut = t.get("statut", "A faire")

        # Colonne 1 : Tache (editable)
        c = ws.cell(row=row, column=1, value=t.get("nom", ""))
        c.font = Font(size=10, bold=True)
        c.protection = Protection(locked=False)

        # Colonne 2 : Responsable (editable)
        c = ws.cell(row=row, column=2, value=t.get("responsable", ""))
        c.protection = Protection(locked=False)

        # Colonnes 3, 4 : dates (editable)
        c = ws.cell(row=row, column=3, value=t.get("debut", ""))
        c.protection = Protection(locked=False)
        c = ws.cell(row=row, column=4, value=t.get("fin", ""))
        c.protection = Protection(locked=False)

        # Colonne 5 : Duree (calculee -> protegee)
        c = ws.cell(row=row, column=5, value=duree)
        c.protection = Protection(locked=True)

        # Colonne 6 : Avancement (editable, numerique 0-100)
        c = ws.cell(row=row, column=6, value=avancement)
        c.protection = Protection(locked=False)

        # Colonne 7 : Statut (editable via dropdown)
        c = ws.cell(row=row, column=7, value=statut)
        c.protection = Protection(locked=False)

        # Colonne 8 : Progression (vide, sera remplie par DataBar)
        c = ws.cell(row=row, column=8, value=avancement)
        c.protection = Protection(locked=True)

        # Style ligne
        statut_bg = STATUT_STYLES.get(statut, COLOR_GRAY)
        for col in range(1, 9):
            cell = ws.cell(row=row, column=col)
            cell.border = _thin_border()
            cell.alignment = Alignment(
                vertical="center",
                horizontal="center" if col in (3, 4, 5, 6, 7, 8) else "left",
            )
        ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor=statut_bg)

        ws.row_dimensions[row].height = 22
        row += 1

    last_data_row = row - 1

    # Colonnes
    widths = [40, 20, 12, 12, 10, 14, 14, 18]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Figer l'en-tete
    ws.freeze_panes = "A6"

    # DataBar sur colonne 8 (PROGRESSION) - vraie barre visuelle
    if last_data_row >= first_data_row:
        rule = DataBarRule(
            start_type="num", start_value=0,
            end_type="num", end_value=100,
            color="2563EB", showValue=True,
        )
        ws.conditional_formatting.add(
            f"H{first_data_row}:H{last_data_row}", rule
        )

    # Dropdown statut sur colonne 7
    if last_data_row >= first_data_row:
        dv = DataValidation(
            type="list",
            formula1=f'"{",".join(STATUTS_VALIDES)}"',
            allow_blank=False,
            showDropDown=False,  # False = affiche le dropdown (contre-intuitif)
        )
        dv.error = "Statut invalide. Choisis dans la liste."
        dv.errorTitle = "Erreur"
        ws.add_data_validation(dv)
        dv.add(f"G{first_data_row}:G{last_data_row}")

    # Validation avancement 0-100
    if last_data_row >= first_data_row:
        dv2 = DataValidation(type="whole", operator="between",
                              formula1="0", formula2="100",
                              allow_blank=True)
        dv2.error = "L'avancement doit etre entre 0 et 100."
        dv2.errorTitle = "Erreur"
        ws.add_data_validation(dv2)
        dv2.add(f"F{first_data_row}:F{last_data_row}")

    # Protection de la feuille
    ws.protection.sheet = True
    ws.protection.password = "memolibdev"
    ws.protection.formatCells = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False

    # Resume
    row += 1
    ws.merge_cells(f"A{row}:H{row}")
    total = len(taches)
    termines = sum(1 for t in taches if t.get("statut") in ("Termine", "Terminé"))
    en_cours = sum(1 for t in taches if t.get("statut") == "En cours")
    en_retard = sum(1 for t in taches if t.get("statut") == "En retard")
    avg = int(round(sum(t.get("avancement", 0) for t in taches) / total)) if total else 0

    c = ws.cell(row=row, column=1)
    c.value = f"RESUME : {total} taches | {termines} terminees | {en_cours} en cours | {en_retard} en retard | Avancement : {avg}%"
    c.font = Font(size=10, bold=True, color=COLOR_ACCENT)
    c.fill = PatternFill("solid", fgColor=COLOR_GRAY)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 24
    c.protection = Protection(locked=True)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
