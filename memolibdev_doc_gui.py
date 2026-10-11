#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MemoLibDev - GUI generation de documents."""
import os, sys, threading
from datetime import datetime, timedelta
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from document_engine import render_template
from document_engine.renderers.pdf import render_pdf
from document_engine.fields import load_fields, champs_manquants, appliquer_defauts

BG = "#0d1117"
CARD = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#2563eb"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

TEMPLATES = {
    "facture":      "FACTURE",
    "devis":        "DEVIS",
    "compte-rendu": "COMPTE RENDU",
    "attestation":  "ATTESTATION",
    "rapport":      "RAPPORT",
    "planning":     "PLANNING",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MemoLibDev - Documents")
        self.geometry("1100x780")
        self.minsize(900, 600)
        self.configure(fg_color=BG)
        self.update_idletasks()
        w, h = 1100, 780
        x = (self.winfo_screenwidth() - w) // 2
        y = max(20, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.template_id = "facture"
        self.fields = {}
        self.vars = {}
        self.lignes = []
        self.lignes_frame = None
        self.template_dir = None

        self._build()
        self._load("facture")

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sb = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, width=220)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)

        ctk.CTkLabel(sb, text="MemoLibDev",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=ACCENT).pack(pady=(20, 2), padx=16, anchor="w")
        ctk.CTkLabel(sb, text="Generateur de documents",
                     font=ctk.CTkFont(size=10, slant="italic"),
                     text_color=MUTED).pack(padx=16, anchor="w")
        ctk.CTkLabel(sb, text="MODELES",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=MUTED).pack(pady=(24, 6), padx=16, anchor="w")

        self.buttons = {}
        for tid, label in TEMPLATES.items():
            b = ctk.CTkButton(sb, text=f"   {label}", anchor="w", height=40,
                              fg_color="transparent", hover_color="#21262d",
                              text_color=TEXT, font=ctk.CTkFont(size=12),
                              command=lambda t=tid: self._load(t))
            b.pack(fill="x", padx=12, pady=2)
            self.buttons[tid] = b

        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(main, fg_color=BG, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        self.hdr_title = ctk.CTkLabel(hdr, text="FACTURE",
                                       font=ctk.CTkFont(size=22, weight="bold"),
                                       text_color=TEXT)
        self.hdr_title.pack(anchor="w")

        self.form = ctk.CTkScrollableFrame(main, fg_color=CARD, corner_radius=12)
        self.form.grid(row=1, column=0, sticky="nsew", padx=24, pady=8)

        bar = ctk.CTkFrame(main, fg_color=BG, corner_radius=0, height=70)
        bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 20))
        bar.grid_propagate(False)

        self.status = ctk.CTkLabel(bar, text="Pret",
                                    font=ctk.CTkFont(size=10, slant="italic"),
                                    text_color=MUTED)
        self.status.pack(side="left", padx=4)

        self.btn_gen = ctk.CTkButton(bar, text="  Generer le document",
                                      command=self._generate,
                                      height=44, width=240,
                                      fg_color=ACCENT, hover_color="#1d4ed8",
                                      text_color="white",
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_gen.pack(side="right", padx=4)

        ctk.CTkButton(bar, text="Effacer",
                       command=lambda: self._load(self.template_id),
                       height=44, width=120,
                       fg_color=CARD, hover_color="#21262d",
                       border_width=1, border_color=BORDER,
                       text_color=TEXT).pack(side="right", padx=4)

    def _load(self, tid):
        self.template_id = tid
        tdir = ROOT / "templates" / tid
        if not tdir.is_dir():
            messagebox.showerror("Erreur", f"Template introuvable : {tid}")
            return
        for t, b in self.buttons.items():
            b.configure(fg_color=ACCENT if t == tid else "transparent",
                         text_color="white" if t == tid else TEXT)
        self.hdr_title.configure(text=TEMPLATES[tid])
        self.template_dir = tdir
        self.vars = {}
        self.lignes = []
        self.lignes_frame = None
        try:
            self.fields = load_fields(tdir)
        except Exception as e:
            messagebox.showerror("Erreur", f"fields.json : {e}")
            return
        self._render()

    def _render(self):
        for w in self.form.winfo_children():
            w.destroy()
        for chemin, spec in self.fields.get("champs", {}).items():
            if chemin == "lignes":
                continue
            self._render_field(chemin, spec)
        if "lignes" in self.fields.get("champs", {}):
            self._render_lignes()

    def _render_field(self, chemin, spec):
        row = ctk.CTkFrame(self.form, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=8)
        label = spec.get("question", chemin)
        if spec.get("obligatoire"):
            label += " *"
        if spec.get("exemple") and not spec.get("defaut"):
            label += f"   (ex. : {spec['exemple']})"
        ctk.CTkLabel(row, text=label, anchor="w",
                      font=ctk.CTkFont(size=11),
                      text_color=TEXT).pack(fill="x")
        var = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=var, fg_color=BG,
                      border_color=BORDER, text_color=TEXT, height=36).pack(
            fill="x", pady=(4, 0))
        d = spec.get("defaut", "")
        if d == "aujourd'hui":
            var.set(datetime.now().strftime("%d/%m/%Y"))
        elif d == "+30 jours":
            var.set((datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y"))
        elif d and d not in ("auto",):
            var.set(str(d))
        self.vars[chemin] = var

    def _render_lignes(self):
        sec = ctk.CTkFrame(self.form, fg_color=BG, corner_radius=8)
        sec.pack(fill="x", padx=18, pady=12)
        hdr = ctk.CTkFrame(sec, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(hdr, text="LIGNES  *",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=ACCENT).pack(side="left")
        ctk.CTkButton(hdr, text="+ Ajouter", command=self._add_ligne,
                       width=110, height=30, fg_color=ACCENT,
                       hover_color="#1d4ed8", text_color="white",
                       font=ctk.CTkFont(size=11, weight="bold")).pack(side="right")
        self.lignes_frame = ctk.CTkFrame(sec, fg_color="transparent")
        self.lignes_frame.pack(fill="x", padx=12, pady=(0, 12))
        self._refresh_lignes()

    def _refresh_lignes(self):
        if self.lignes_frame is None:
            return
        for w in self.lignes_frame.winfo_children():
            w.destroy()
        if not self.lignes:
            ctk.CTkLabel(self.lignes_frame,
                          text="Aucune ligne. Cliquez sur '+ Ajouter'.",
                          font=ctk.CTkFont(size=10, slant="italic"),
                          text_color=MUTED).pack(anchor="w", pady=6)
            return
        for i, l in enumerate(self.lignes):
            card = ctk.CTkFrame(self.lignes_frame, fg_color=CARD,
                                 corner_radius=8, border_width=1,
                                 border_color=BORDER)
            card.pack(fill="x", pady=4)
            card.grid_columnconfigure(0, weight=4)
            card.grid_columnconfigure(1, weight=1)
            card.grid_columnconfigure(2, weight=2)
            vd = ctk.StringVar(value=l.get("description", ""))
            ctk.CTkEntry(card, textvariable=vd, placeholder_text="Description",
                          fg_color=BG, border_color=BORDER, height=32).grid(
                row=0, column=0, sticky="ew", padx=(8, 4), pady=8)
            vd.trace_add("write", lambda *a, l=l, v=vd: l.update({"description": v.get()}))
            vq = ctk.StringVar(value=str(l.get("quantite", 1)))
            ctk.CTkEntry(card, textvariable=vq, width=60,
                          fg_color=BG, border_color=BORDER, height=32).grid(
                row=0, column=1, sticky="ew", padx=4, pady=8)
            vq.trace_add("write", lambda *a, l=l, v=vq: l.update({"quantite": v.get()}))
            vp = ctk.StringVar(value=str(l.get("prix_ht", "")))
            ctk.CTkEntry(card, textvariable=vp, placeholder_text="Prix HT",
                          fg_color=BG, border_color=BORDER, height=32).grid(
                row=0, column=2, sticky="ew", padx=4, pady=8)
            vp.trace_add("write", lambda *a, l=l, v=vp: l.update({"prix_ht": v.get()}))
            ctk.CTkButton(card, text="X", command=lambda i=i: self._remove_ligne(i),
                           width=32, height=32, fg_color="transparent",
                           hover_color="#7f1d1d", text_color=ERROR,
                           font=ctk.CTkFont(size=13, weight="bold")).grid(
                row=0, column=3, padx=(4, 8), pady=8)

    def _add_ligne(self):
        self.lignes.append({"description": "", "quantite": "1",
                             "prix_ht": "", "tva_pct": "20"})
        self._refresh_lignes()

    def _remove_ligne(self, i):
        if 0 <= i < len(self.lignes):
            del self.lignes[i]
            self._refresh_lignes()

    def _collect(self):
        data = {}
        for chemin, var in self.vars.items():
            v = var.get().strip()
            if not v:
                continue
            parts = chemin.split(".")
            cur = data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = v
        lp = []
        for l in self.lignes:
            if not l.get("description", "").strip():
                continue
            try:
                q = int(str(l.get("quantite", "1")).strip() or "1")
            except ValueError:
                q = 1
            try:
                p = float(str(l.get("prix_ht", "0")).replace(",", ".") or "0")
            except ValueError:
                p = 0.0
            lp.append({"description": l["description"].strip(),
                       "quantite": q, "prix_ht": p,
                       "tva_pct": str(l.get("tva_pct", "20"))})
        if lp:
            data["lignes"] = lp
        return data

    def _generate(self):
        data = self._collect()
        manquants = champs_manquants(self.fields, data)
        if manquants:
            noms = "\n  - ".join(m["question"] for m in manquants)
            messagebox.showwarning("Champs obligatoires manquants",
                                    f"Merci de remplir :\n\n  - {noms}")
            return
        data = appliquer_defauts(self.fields, data)
        self.btn_gen.configure(state="disabled", text="  Generation...")
        self.status.configure(text="Generation en cours...", text_color=WARNING)

        def worker():
            try:
                html = render_template(self.template_dir, data)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out = ROOT / "dist" / f"{self.template_id}_{ts}.pdf"
                out.parent.mkdir(parents=True, exist_ok=True)
                render_pdf(html, output_path=out)
                self.after(0, lambda: self._done(out))
            except Exception as e:
                self.after(0, lambda: self._err(e))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, out):
        self.btn_gen.configure(state="normal", text="  Generer le document")
        self.status.configure(text=f"OK : {out.name}", text_color=SUCCESS)
        messagebox.showinfo("Succes", f"Document genere :\n\n{out}")
        try:
            os.startfile(str(out))
        except Exception:
            pass

    def _err(self, e):
        self.btn_gen.configure(state="normal", text="  Generer le document")
        self.status.configure(text=f"Erreur : {type(e).__name__}", text_color=ERROR)
        messagebox.showerror("Erreur", str(e))


if __name__ == "__main__":
    App().mainloop()
