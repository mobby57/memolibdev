from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime


APP_NAME = "MemoLibDev V3.5.1"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

V3_ROOT = Path(__file__).resolve().parent.parent

# Autorise l'interface située dans interface\\ à importer
# les modules Python situés à la racine de MemoLibDev V3.
if str(V3_ROOT) not in sys.path:
    sys.path.insert(0, str(V3_ROOT))

import web_research
from interface.diagnostics import (
    StepDiagnosticFailure,
    failed_step,
    inspection_failure,
    ollama_failure,
    successful_step,
    timing_summary,
    web_research_diagnostic,
)
MEMOLIB_ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
INSPECTOR = V3_ROOT / "inspector.py"
REPORTS_DIR = V3_ROOT / "reports"

MAX_CONTEXT_CHARS = 8000
MAX_FILES = 12

# Budget V2 : limite par fichier pour le modèle local.
MAX_FILE_CONTEXT_CHARS = 2500

# Web Research : lecture seule, contexte limité avant Ollama.
MAX_WEB_CONTEXT_CHARS = 4000


class MemoLibDevApp(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1200x760")
        self.minsize(1000, 650)

        self.configure(bg="#0f172a")

        self.status_vars = {
            "Ollama": tk.StringVar(value="● Vérification..."),
            "Planner": tk.StringVar(value="● Disponible"),
            "Inspector": tk.StringVar(value="● Lecture seule"),
            "Coder": tk.StringVar(value="● Proposition uniquement"),
            "Reviewer": tk.StringVar(value="● Disponible"),
            "Apply": tk.StringVar(value="🔒 Validation humaine"),
        }

        self._build_style()
        self._build_ui()

        self._append_system(
            "MemoLibDev V3.5.1 démarré.\n"
            "Mode sécurisé : inspection réelle de MemoLib en lecture seule.\n"
            "Aucune modification, aucun commit, aucun push."
        )

        self.after(300, self.check_ollama)

    # ---------------------------------------------------------
    # STYLE
    # ---------------------------------------------------------

    def _build_style(self):
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Tree.TFrame",
            background="#111827"
        )

        style.configure(
            "Title.TLabel",
            background="#0f172a",
            foreground="#f8fafc",
            font=("Segoe UI", 20, "bold")
        )

        style.configure(
            "Subtitle.TLabel",
            background="#0f172a",
            foreground="#94a3b8",
            font=("Segoe UI", 10)
        )

        style.configure(
            "Send.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(18, 10)
        )

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def _build_ui(self):

        header = tk.Frame(
            self,
            bg="#0f172a",
            height=70
        )
        header.pack(fill="x", padx=24, pady=(18, 8))
        header.pack_propagate(False)

        ttk.Label(
            header,
            text="MemoLibDev",
            style="Title.TLabel"
        ).pack(side="left")

        ttk.Label(
            header,
            text="  V3.5.1  •  Agent de développement local",
            style="Subtitle.TLabel"
        ).pack(side="left", padx=(8, 0), pady=(8, 0))

        self.ollama_badge = tk.Label(
            header,
            textvariable=self.status_vars["Ollama"],
            bg="#111827",
            fg="#94a3b8",
            padx=14,
            pady=7,
            font=("Segoe UI", 9, "bold")
        )
        self.ollama_badge.pack(side="right")

        main = tk.Frame(
            self,
            bg="#0f172a"
        )
        main.pack(
            fill="both",
            expand=True,
            padx=18,
            pady=(0, 18)
        )

        self._build_sidebar(main)
        self._build_chat(main)

    def _build_sidebar(self, parent):

        sidebar = tk.Frame(
            parent,
            bg="#111827",
            width=245
        )
        sidebar.pack(
            side="left",
            fill="y",
            padx=(0, 12)
        )
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar,
            text="PROJET",
            bg="#111827",
            fg="#64748b",
            font=("Segoe UI", 9, "bold")
        ).pack(
            anchor="w",
            padx=18,
            pady=(20, 5)
        )

        tk.Label(
            sidebar,
            text="MemoLib",
            bg="#111827",
            fg="#f8fafc",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=18
        )

        tk.Label(
            sidebar,
            text=str(MEMOLIB_ROOT),
            bg="#111827",
            fg="#64748b",
            font=("Consolas", 8)
        ).pack(
            anchor="w",
            padx=18,
            pady=(3, 18)
        )

        tk.Label(
            sidebar,
            text="WORKFLOW",
            bg="#111827",
            fg="#64748b",
            font=("Segoe UI", 9, "bold")
        ).pack(
            anchor="w",
            padx=18,
            pady=(5, 8)
        )

        for name in [
            "Planner",
            "Inspector",
            "Coder",
            "Reviewer",
            "Apply",
        ]:
            tk.Label(
                sidebar,
                textvariable=self.status_vars[name],
                bg="#111827",
                fg="#cbd5e1",
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                padx=22,
                pady=4
            )

        separator = tk.Frame(
            sidebar,
            bg="#1f2937",
            height=1
        )
        separator.pack(
            fill="x",
            padx=18,
            pady=18
        )

        tk.Label(
            sidebar,
            text="SÉCURITÉ",
            bg="#111827",
            fg="#64748b",
            font=("Segoe UI", 9, "bold")
        ).pack(
            anchor="w",
            padx=18
        )

        safety = [
            "✓ Lecture seule",
            "✓ Pas de commit automatique",
            "✓ Pas de push automatique",
            "✓ Pas de production",
            "✓ Validation humaine",
        ]

        for item in safety:
            tk.Label(
                sidebar,
                text=item,
                bg="#111827",
                fg="#94a3b8",
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                padx=22,
                pady=3
            )

    def _build_chat(self, parent):

        chat = tk.Frame(
            parent,
            bg="#111827"
        )
        chat.pack(
            side="left",
            fill="both",
            expand=True
        )

        tk.Label(
            chat,
            text="Conversation",
            bg="#111827",
            fg="#f8fafc",
            font=("Segoe UI", 13, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(18, 10)
        )

        text_frame = tk.Frame(
            chat,
            bg="#0b1120"
        )
        text_frame.pack(
            fill="both",
            expand=True,
            padx=14
        )

        self.chat = tk.Text(
            text_frame,
            bg="#0b1120",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            selectbackground="#334155",
            relief="flat",
            borderwidth=0,
            wrap="word",
            font=("Segoe UI", 10),
            padx=18,
            pady=18
        )

        scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.chat.yview
        )

        self.chat.configure(
            yscrollcommand=scrollbar.set
        )

        self.chat.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.chat.tag_configure(
            "system",
            foreground="#94a3b8"
        )

        self.chat.tag_configure(
            "user",
            foreground="#60a5fa"
        )

        self.chat.tag_configure(
            "agent",
            foreground="#f8fafc"
        )

        input_frame = tk.Frame(
            chat,
            bg="#111827"
        )
        input_frame.pack(
            fill="x",
            padx=14,
            pady=14
        )

        self.input = tk.Text(
            input_frame,
            height=4,
            bg="#1e293b",
            fg="#f8fafc",
            insertbackground="#ffffff",
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
            padx=12,
            pady=10
        )

        self.input.pack(
            side="left",
            fill="x",
            expand=True
        )

        self.input.bind(
            "<Control-Return>",
            lambda event: self.send_message()
        )

        send = ttk.Button(
            input_frame,
            text="Envoyer\nCtrl+Entrée",
            style="Send.TButton",
            command=self.send_message
        )

        send.pack(
            side="right",
            padx=(10, 0)
        )

    # ---------------------------------------------------------
    # CHAT
    # ---------------------------------------------------------

    def _append_system(self, text):

        self.chat.insert(
            "end",
            f"\nMemoLibDev\n{text}\n",
            "system"
        )

        self.chat.see("end")

    def _append_user(self, text):

        self.chat.insert(
            "end",
            f"\nVous\n{text}\n",
            "user"
        )

        self.chat.see("end")

    def _append_agent(self, text):

        self.chat.insert(
            "end",
            f"\nAgent\n{text}\n",
            "agent"
        )

        self.chat.see("end")

    def send_message(self):

        request = self.input.get("1.0", "end").strip()

        if not request:
            return

        self.input.delete("1.0", "end")

        self._append_user(request)

        self.status_vars["Planner"].set(
            "● Préparation..."
        )

        self.status_vars["Inspector"].set(
            "● Inspection..."
        )

        thread = threading.Thread(
            target=self._inspect_and_ask,
            args=(request,),
            daemon=True
        )

        thread.start()

    # ---------------------------------------------------------
    # INTELLIGENT INSPECTION
    # ---------------------------------------------------------

    def _detect_keywords(self, request: str) -> list[str]:

        text = request.lower()

        keyword_groups = {
            "clerk": [
                "clerk",
                "connexion",
                "connection",
                "login",
                "auth",
                "authentification",
                "sign-in",
                "signin",
                "session",
            ],
            "proxy": [
                "proxy",
                "middleware",
                "route",
                "matcher",
            ],
            "email": [
                "email",
                "mail",
                "gmail",
                "outlook",
                "sendgrid",
                "resend",
            ],
            "prisma": [
                "prisma",
                "database",
                "base de données",
                "postgres",
                "neon",
            ],
            "ai": [
                "ia",
                "ai",
                "ollama",
                "modèle",
                "model",
            ],
        }

        detected = []

        for group, words in keyword_groups.items():

            if any(word in text for word in words):
                detected.append(group)

        return detected

    def _candidate_files(
        self,
        request: str
    ) -> list[Path]:
        """
        Sélectionne les fichiers les plus pertinents pour une demande.

        Priorité V2.1 :
        1. middleware / proxy ;
        2. Clerk / authentification ;
        3. OAuth / session ;
        4. configuration ;
        5. routes API ;
        6. pages d'authentification ;
        7. tests en dernier recours.

        Objectif :
        empêcher les tests ou pages secondaires de remplacer
        les fichiers d'infrastructure indispensables au diagnostic.
        """

        selected_keywords = [
            word
            for word in re.findall(
                r"[A-Za-zÀ-ÿ0-9_./\\-]+",
                request.lower()
            )
            if len(word) >= 3
        ]

        allowed_extensions = {
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
            ".json",
        }

        ignored_dirs = {
            "node_modules",
            ".git",
            ".next",
            "dist",
            "build",
            "coverage",
            "__pycache__",
        }

        candidates = []

        for root, dirs, files in os.walk(
            MEMOLIB_ROOT,
            topdown=True,
            followlinks=False,
        ):
            dirs[:] = [
                d for d in dirs
                if d not in ignored_dirs
                and not d.startswith(".next")
            ]

            for filename in files:

                file_path = Path(root) / filename

                if file_path.suffix.lower() not in allowed_extensions:
                    continue

                try:
                    relative = file_path.relative_to(
                        MEMOLIB_ROOT
                    )
                except ValueError:
                    continue

                relative_str = str(relative).replace(
                    "\\",
                    "/"
                )

                lower = relative_str.lower()

                score = 0

                # -------------------------------------------------
                # TESTS : FORTE PENALITE
                # -------------------------------------------------

                is_test = (
                    "/__tests__/" in lower
                    or "/tests/" in lower
                    or lower.endswith(".test.ts")
                    or lower.endswith(".test.tsx")
                    or lower.endswith(".spec.ts")
                    or lower.endswith(".spec.tsx")
                )

                if is_test:
                    score -= 150

                # -------------------------------------------------
                # PRODUCTION : PRIORITE GENERALE
                # -------------------------------------------------

                if not is_test:
                    score += 100

                # -------------------------------------------------
                # MIDDLEWARE / PROXY : PRIORITE MAXIMALE
                # -------------------------------------------------

                if filename.lower() in {
                    "proxy.ts",
                    "proxy.js",
                    "middleware.ts",
                    "middleware.js",
                    "middleware.tsx",
                    "middleware.jsx",
                }:
                    score += 300

                if "middleware" in lower:
                    score += 180

                if "proxy." in lower:
                    score += 180

                # -------------------------------------------------
                # CLERK / AUTH
                # -------------------------------------------------

                if "clerk" in lower:
                    score += 180

                if any(
                    marker in lower
                    for marker in [
                        "/auth/",
                        "/authentication/",
                        "auth.",
                        "auth/",
                        "clerk-token",
                        "clerk_auth",
                        "clerk-auth",
                    ]
                ):
                    score += 160

                # -------------------------------------------------
                # OAUTH / SESSION
                # -------------------------------------------------

                if "oauth" in lower:
                    score += 130

                if "session" in lower:
                    score += 110

                if "token" in lower:
                    score += 90

                # -------------------------------------------------
                # CONFIGURATION
                # -------------------------------------------------

                if filename.lower() == "package.json":
                    score += 170

                # -------------------------------------------------
                # ROUTES API
                # -------------------------------------------------

                if "/api/" in lower:
                    score += 80

                if "/route." in lower:
                    score += 70

                # -------------------------------------------------
                # LOGIN / AUTH PAGES
                # -------------------------------------------------

                if "/login/" in lower:
                    score += 55

                if lower.endswith("/login/page.tsx"):
                    score += 50

                if lower.endswith("/login/page.ts"):
                    score += 50

                # -------------------------------------------------
                # LAYOUTS
                # -------------------------------------------------

                if "layout." in lower:
                    score += 25

                # -------------------------------------------------
                # CORRESPONDANCE AVEC LA DEMANDE
                # -------------------------------------------------

                for keyword in selected_keywords:

                    if keyword in lower:
                        score += 20

                # -------------------------------------------------
                # PENALITE FICHIERS NON PROD / AUXILIAIRES
                # -------------------------------------------------

                if any(
                    marker in lower
                    for marker in [
                        "/fixtures/",
                        "/mocks/",
                        "/mock/",
                        "/snapshots/",
                        "/storybook/",
                    ]
                ):
                    score -= 100

                candidates.append(
                    (
                        score,
                        relative_str
                    )
                )

        # ---------------------------------------------------------
        # TRI DETERMINISTE
        # ---------------------------------------------------------

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].lower(),
            )
        )

        return [
            Path(relative)
            for score, relative
            in candidates[:MAX_FILES]
        ]
    def _run_inspector(self, files: list) -> dict:
        """
        Lance inspector.py en lecture seule et récupère
        exactement le rapport produit par CETTE inspection.
        """
        normalized = []

        for item in files:
            try:
                candidate = Path(item)

                if candidate.is_absolute():
                    absolute = candidate.resolve()
                else:
                    absolute = (MEMOLIB_ROOT / candidate).resolve()

                try:
                    relative = absolute.relative_to(MEMOLIB_ROOT)
                except ValueError:
                    continue

                # Vérification réelle du fichier dans MemoLib.
                if not absolute.exists() or not absolute.is_file():
                    continue

                normalized.append(str(relative).replace("\\", "/"))

            except (OSError, ValueError, TypeError):
                continue

        normalized = list(dict.fromkeys(normalized))

        if not normalized:
            raise RuntimeError(
                "Aucun fichier sûr et réellement présent à inspecter."
            )

        reports_dir = REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)

        # État AVANT inspection.
        before = {
            p.resolve()
            for p in reports_dir.glob("inspection-*.json")
            if p.is_file()
        }

        command = [
            sys.executable,
            str(INSPECTOR),
            *normalized,
        ]

        result = subprocess.run(
            command,
            cwd=str(V3_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"Inspection échouée (code {result.returncode}) : {detail}"
            )

        # Cherche d'abord un nouveau rapport créé pendant cette exécution.
        after = [
            p.resolve()
            for p in reports_dir.glob("inspection-*.json")
            if p.is_file()
        ]

        new_reports = [
            p for p in after
            if p not in before
        ]

        if new_reports:
            latest = max(
                new_reports,
                key=lambda p: p.stat().st_mtime_ns,
            )
        elif after:
            # Fallback robuste : dernier rapport modifié.
            latest = max(
                after,
                key=lambda p: p.stat().st_mtime_ns,
            )
        else:
            raise RuntimeError(
                f"Inspection terminée mais aucun rapport trouvé dans : "
                f"{reports_dir}"
            )

        try:
            report = json.loads(
                latest.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise RuntimeError(
                f"Rapport d'inspection illisible : {latest} — {exc}"
            ) from exc

        # Preuve technique conservée dans le contexte.
        report["_memoLibDev"] = {
            "requested_files": normalized,
            "inspected_count": len(normalized),
            "report": str(latest),
            "new_report": latest in new_reports,
            "read_only": True,
        }

        return report

    def _build_context(
        self,
        inspection: list[dict]
    ) -> str:
        """
        Construit un contexte compact pour Ollama.

        V2.2 :
        - réserve explicitement les fichiers critiques Auth/Clerk ;
        - évite qu'un grand nombre de routes OAuth monopolise le budget ;
        - conserve un budget global strict ;
        - aucun secret n'est transmis ;
        - les tests restent en dernier recours.
        """

        # -------------------------------------------------
        # 1. FILTRAGE INITIAL
        # -------------------------------------------------

        eligible = []

        for index, item in enumerate(inspection):

            if not item.get("exists"):
                continue

            relative = item.get(
                "requested_path",
                "inconnu"
            )

            content = item.get(
                "content",
                ""
            )

            if not content:
                continue

            lowered = relative.lower()

            # Ne jamais envoyer de secrets.
            if any(
                secret_name in lowered
                for secret_name in [
                    ".env",
                    "secret",
                    "credential",
                    "credentials",
                    "private-key",
                    "private_key",
                ]
            ):
                continue

            # -------------------------------------------------
            # TEST
            # -------------------------------------------------

            is_test = (
                "/__tests__/" in lowered
                or "/tests/" in lowered
                or lowered.endswith(".test.ts")
                or lowered.endswith(".test.tsx")
                or lowered.endswith(".spec.ts")
                or lowered.endswith(".spec.tsx")
            )

            # -------------------------------------------------
            # CATEGORIES
            # -------------------------------------------------

            is_middleware = (
                lowered.endswith("/middleware.ts")
                or lowered.endswith("/middleware.js")
                or lowered.endswith("/middleware.tsx")
                or lowered.endswith("/middleware.jsx")
                or "/middleware/" in lowered
            )

            is_proxy = (
                lowered.endswith("/proxy.ts")
                or lowered.endswith("/proxy.js")
                or lowered.endswith("/proxy.tsx")
                or lowered.endswith("/proxy.jsx")
            )

            is_clerk = (
                "clerk" in lowered
                or "clerk-auth" in lowered
                or "clerk_auth" in lowered
                or "clerk-token" in lowered
            )

            is_auth = (
                "/auth/" in lowered
                or "/authentication/" in lowered
                or "/auth." in lowered
                or lowered.endswith("/auth.ts")
                or lowered.endswith("/auth.js")
            )

            is_oauth = (
                "oauth" in lowered
            )

            is_session = (
                "session" in lowered
            )

            is_config = (
                lowered.endswith("package.json")
            )

            is_api_route = (
                "/api/" in lowered
                and "/route." in lowered
            )

            is_login = (
                "/login/" in lowered
                or lowered.endswith("/login/page.tsx")
                or lowered.endswith("/login/page.ts")
            )

            # -------------------------------------------------
            # SCORE
            # -------------------------------------------------

            score = 0

            if not is_test:
                score += 100
            else:
                score -= 200

            # Infrastructure critique.
            if is_proxy:
                score += 500

            if is_middleware:
                score += 480

            if is_clerk:
                score += 300

            if is_auth:
                score += 260

            if is_session:
                score += 180

            # Configuration.
            if is_config:
                score += 220

            # OAuth : important mais après Auth/Middleware.
            if is_oauth:
                score += 70

            # Routes API.
            if is_api_route:
                score += 40

            # Login.
            if is_login:
                score += 20

            # Demande utilisateur.
            for keyword in re.findall(
                r"[A-Za-zÀ-ÿ0-9_./\\-]+",
                "auth clerk middleware",
            ):
                if len(keyword) >= 3 and keyword in lowered:
                    score += 25

            eligible.append(
                {
                    "score": score,
                    "index": index,
                    "item": item,
                    "path": relative,
                    "lower": lowered,
                    "content": content,
                    "is_test": is_test,
                    "is_middleware": is_middleware,
                    "is_proxy": is_proxy,
                    "is_clerk": is_clerk,
                    "is_auth": is_auth,
                    "is_oauth": is_oauth,
                    "is_config": is_config,
                }
            )

        # -------------------------------------------------
        # 2. TRI GENERAL
        # -------------------------------------------------

        eligible.sort(
            key=lambda entry: (
                -entry["score"],
                entry["index"],
            )
        )

        # -------------------------------------------------
        # 3. RESERVATION CRITIQUE
        #
        # On réserve d'abord les fichiers d'infrastructure
        # réellement présents dans l'inspection.
        # -------------------------------------------------

        critical = []
        used_paths = set()

        for entry in eligible:

            if entry["is_test"]:
                continue

            critical_match = (
                entry["is_proxy"]
                or entry["is_middleware"]
                or entry["is_clerk"]
                or entry["is_auth"]
            )

            if not critical_match:
                continue

            path_key = entry["path"].lower()

            if path_key in used_paths:
                continue

            critical.append(entry)
            used_paths.add(path_key)

        # -------------------------------------------------
        # 4. LIMITER LES CRITIQUES
        #
        # Maximum 5 fichiers critiques.
        # Cela empêche plusieurs dizaines de fichiers auth
        # de remplir tout le contexte.
        # -------------------------------------------------

        critical = critical[:5]

        # -------------------------------------------------
        # 5. COMPLEMENT
        # -------------------------------------------------

        selected = list(critical)

        for entry in eligible:

            if len(selected) >= MAX_FILES:
                break

            path_key = entry["path"].lower()

            if path_key in used_paths:
                continue

            selected.append(entry)
            used_paths.add(path_key)

        # -------------------------------------------------
        # 6. CONSTRUCTION DU CONTEXTE
        # -------------------------------------------------

        chunks = []
        total = 0

        # Les fichiers critiques ont un budget individuel
        # suffisant pour contenir les imports / fonctions
        # d'authentification importantes.
        critical_limit = 1600

        # Les fichiers complémentaires sont plus courts.
        normal_limit = 1000

        for entry in selected:

            if total >= MAX_CONTEXT_CHARS:
                break

            relative = entry["path"]
            content = entry["content"]

            if entry in critical:
                file_limit = critical_limit
            else:
                file_limit = normal_limit

            excerpt = content[:file_limit]

            block = (
                f"\n===== FICHIER RÉEL : {relative} =====\n"
                f"{excerpt}\n"
                f"===== FIN : {relative} =====\n"
            )

            remaining = (
                MAX_CONTEXT_CHARS - total
            )

            if len(block) > remaining:

                if remaining < 500:
                    break

                excerpt = content[
                    :max(0, remaining - 120)
                ]

                block = (
                    f"\n===== FICHIER RÉEL : {relative} =====\n"
                    f"{excerpt}\n"
                    f"===== FIN : {relative} =====\n"
                )

            if not block.strip():
                continue

            chunks.append(block)
            total += len(block)

        return "".join(chunks)
    # ---------------------------------------------------------
    # WEB RESEARCH
    # ---------------------------------------------------------

    def _run_web_research(self, request):
        """
        Recherche Web publique en lecture seule.

        Le Web ne reçoit aucun fichier local ni secret.
        Les résultats restent séparés des faits Inspector.
        """

        try:
            self.after(
                0,
                lambda: self.status_vars[
                    "Inspector"
                ].set(
                    "● Recherche Web en cours..."
                )
            )

            report = web_research.research(request)

            return {
                "success": True,
                "question": request,
                "sources": report.get("sources", []),
                "engine": report.get(
                    "engine",
                    "github-api+jina-reader"
                ),
                "read_only": report.get(
                    "read_only",
                    True
                ),
            }

        except Exception as exc:
            return {
                "success": False,
                "question": request,
                "sources": [],
                "engine": "github-api+jina-reader",
                "read_only": True,
                "error": str(exc),
            }


    def _build_web_context(self, web_report):
        """
        Construit un contexte Web limité pour Ollama.
        """

        if not isinstance(web_report, dict):
            return ""

        sources = web_report.get("sources", [])

        if not isinstance(sources, list):
            return ""

        chunks = []
        total = 0

        for index, source in enumerate(
            sources,
            start=1
        ):

            if not isinstance(source, dict):
                continue

            url = str(
                source.get("url", "")
            ).strip()

            if not url:
                continue

            title = str(
                source.get("title", url)
            ).strip()

            source_type = str(
                source.get(
                    "source_type",
                    "web"
                )
            ).strip()

            domain = str(
                source.get("domain", "")
            ).strip()

            content = source.get(
                "content",
                ""
            )

            if not content:
                content = source.get(
                    "description",
                    ""
                )

            content = str(
                content
            ).strip()

            if len(content) > 7000:
                content = (
                    content[:2000]
                    + "\n[contenu tronqué]"
                )

            block = (
                f"\n===== SOURCE WEB {index} =====\n"
                f"TYPE : {source_type}\n"
                f"TITRE : {title}\n"
                f"DOMAINE : {domain}\n"
                f"URL : {url}\n"
                f"CONTENU :\n{content}\n"
                f"===== FIN SOURCE WEB {index} =====\n"
            )

            if (
                total + len(block)
                > MAX_WEB_CONTEXT_CHARS
            ):
                break

            chunks.append(block)
            total += len(block)

        return "".join(chunks)


    # INSPECTION + OLLAMA
    # ---------------------------------------------------------

    def _show_diagnostic_failure(self, diagnostic, diagnostics):
        if diagnostic.step_id == "Génération Ollama":
            self.status_vars["Ollama"].set(
                "● Ollama ERREUR"
            )
            self.ollama_badge.configure(
                fg="#f87171"
            )

        self.status_vars["Inspector"].set(
            f"● {diagnostic.error_code}"
        )
        self._append_system(
            f"{diagnostic.user_message()}\n"
            f"Chronométrage : {timing_summary(diagnostics)}"
        )

    def _inspect_and_ask(self, request):

        diagnostics = []
        workflow_started = time.perf_counter()

        try:

            started = time.perf_counter()
            try:
                paths = self._candidate_files(
                    request
                )
            except Exception as exc:
                diagnostic = failed_step(
                    "Sélection",
                    time.perf_counter() - started,
                    exc,
                    error_code="SELECTION_ERROR",
                )
                diagnostics.append(diagnostic)
                raise StepDiagnosticFailure(diagnostic) from exc
            diagnostics.append(
                successful_step(
                    "Sélection",
                    time.perf_counter() - started,
                )
            )

            self.after(
                0,
                lambda: self.status_vars[
                    "Inspector"
                ].set(
                    f"● {len(paths)} fichier(s) ciblé(s)"
                )
            )

            # -------------------------------------------------
            # INSPECTION LOCALE
            # -------------------------------------------------

            started = time.perf_counter()
            try:
                inspection = self._run_inspector(
                    paths
                )
            except Exception as exc:
                diagnostic = inspection_failure(
                    time.perf_counter() - started,
                    exc,
                    120,
                )
                diagnostics.append(diagnostic)
                raise StepDiagnosticFailure(diagnostic) from exc
            diagnostics.append(
                successful_step(
                    "Inspection",
                    time.perf_counter() - started,
                )
            )

            context = self._build_context(
                inspection.get(
                    "files",
                    []
                )
            )

            self.after(
                0,
                lambda: self.status_vars[
                    "Inspector"
                ].set(
                    f"● {len(inspection.get('files', []))} fichier(s) inspecté(s)"
                )
            )

            # -------------------------------------------------
            # RECHERCHE WEB
            # -------------------------------------------------
            #
            # Le Web intervient APRÈS l'inspection locale.
            # Il complète les faits locaux mais ne les remplace
            # jamais.
            #

            started = time.perf_counter()
            try:
                web_report = self._run_web_research(
                    request
                )
            except Exception as exc:
                diagnostic = failed_step(
                    "Recherche Web",
                    time.perf_counter() - started,
                    exc,
                    error_code="WEB_RESEARCH_FAILED",
                )
                diagnostics.append(diagnostic)
                raise StepDiagnosticFailure(diagnostic) from exc
            web_diagnostic = web_research_diagnostic(
                time.perf_counter() - started,
                web_report,
            )
            diagnostics.append(web_diagnostic)

            web_context = self._build_web_context(
                web_report
            )

            self.after(
                0,
                lambda: self.status_vars[
                    "Inspector"
                ].set(
                    f"● Local : "
                    f"{len(inspection.get('files', []))} fichier(s) | "
                    f"Web : "
                    f"{len(web_report.get('sources', []))} source(s)"
                )
            )

            # -------------------------------------------------
            # OLLAMA
            # -------------------------------------------------

            ollama_diagnostic = self._ask_ollama(
                request,
                context,
                inspection.get(
                    "files",
                    []
                ),
                web_context,
                web_report,
            )
            diagnostics.append(ollama_diagnostic)
            if ollama_diagnostic.failed:
                self.after(
                    0,
                    lambda diagnostic=ollama_diagnostic,
                    events=tuple(diagnostics): self._show_diagnostic_failure(
                        diagnostic,
                        list(events),
                    ),
                )
                return

            self.after(
                0,
                lambda summary=timing_summary(diagnostics): self.status_vars[
                    "Inspector"
                ].set(f"● {summary}")
            )

            if web_diagnostic.degraded:
                self.after(
                    0,
                    lambda diagnostic=web_diagnostic: self._append_system(
                        diagnostic.user_message()
                    ),
                )

        except StepDiagnosticFailure as failure:
            self.after(
                0,
                lambda diagnostic=failure.diagnostic,
                events=tuple(diagnostics): self._show_diagnostic_failure(
                    diagnostic,
                    list(events),
                ),
            )

        except Exception as exc:
            diagnostic = failed_step(
                "Orchestration",
                time.perf_counter() - workflow_started,
                exc,
                error_code="WORKFLOW_ERROR",
            )
            diagnostics.append(diagnostic)
            self.after(
                0,
                lambda event=diagnostic,
                events=tuple(diagnostics): self._show_diagnostic_failure(
                    event,
                    list(events),
                ),
            )


    def _ask_ollama(
        self,
        request,
        context,
        paths,
        web_context="",
        web_report=None
    ):
        started = time.perf_counter()

        file_list = "\n".join(
            f"- {item.get('requested_path', 'inconnu')}"
            for item in paths
            if isinstance(item, dict)
        )

        prompt = f"""
Tu es MemoLibDev, agent de développement local
pour le projet MemoLib.

Tu fonctionnes actuellement en MODE CONSEIL / AUDIT.

RÈGLES ABSOLUES :
- ne modifie aucun fichier ;
- ne propose jamais de faux chemins ;
- utilise uniquement les fichiers réellement fournis ;
- ne prétends jamais avoir exécuté une modification ;
- ne lance aucun git commit ;
- ne lance aucun git push ;
- aucune action production ;
- ne demande jamais de secret ;
- ne révèle jamais de valeur de secret ;
- distingue clairement faits observés, hypothèses et recommandations ;
- toute modification devra être validée humainement.

DÉPÔT :
{MEMOLIB_ROOT}

FICHIERS CIBLÉS PAR MEMOLIBDEV :
{file_list if file_list else "Aucun fichier ciblé."}

CONTENU RÉEL INSPECTÉ :
{context if context else "Aucun contenu exploitable n'a été récupéré."}

SOURCES WEB PUBLIQUES :
{web_context if web_context else "Aucune source Web exploitable n'a été récupérée."}

RÈGLES DE FUSION LOCAL + WEB :

1. Les fichiers inspectés localement constituent la seule preuve
   de l'état réel du dépôt MemoLib.

2. Une source Web ne peut jamais prouver qu'un fichier local,
   une route locale, une variable d'environnement locale ou une
   configuration locale existe.

3. Les informations Web servent uniquement à compléter le diagnostic
   avec de la documentation, des migrations, des versions, des API,
   des recommandations techniques ou des informations publiques.

4. Si une information locale et une information Web semblent
   contradictoires, signale la contradiction explicitement.

5. Ne présente jamais une recommandation Web comme un fait observé
   dans MemoLib.

6. Cite les URL Web pertinentes dans ta réponse lorsque tu t'appuies
   dessus.

7. Si aucune source Web ne permet de répondre correctement,
   indique-le au lieu d'inventer.

DEMANDE UTILISATEUR :
{request}

Réponds en français.

Structure ta réponse ainsi :

1. DIAGNOSTIC
2. FICHIERS RÉELLEMENT OBSERVÉS
3. CONSTATS FACTUELS
4. HYPOTHÈSES
5. VÉRIFICATIONS COMPLÉMENTAIRES
6. PROCHAINE ÉTAPE

Si les fichiers fournis ne permettent pas de conclure,
dis-le explicitement.

Ne fabrique aucun fichier, chemin ou configuration.
"""

        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0
            }
        }

        try:

            request_http = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(
                    payload
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json"
                },
                method="POST"
            )

            with urllib.request.urlopen(
                request_http,
                timeout=180
            ) as response:

                data = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

            answer = data.get(
                "response",
                "Réponse Ollama vide."
            )

            self.after(
                0,
                lambda: self._agent_response(
                    answer
                )
            )
            return successful_step(
                "Génération Ollama",
                time.perf_counter() - started,
            )

        except Exception as exc:
            return ollama_failure(
                time.perf_counter() - started,
                exc,
                180,
            )

    def _agent_response(self, answer):

        self.status_vars["Planner"].set(
            "● Disponible"
        )

        self.status_vars["Inspector"].set(
            "● Lecture seule"
        )

        self._append_agent(answer)

    # ---------------------------------------------------------
    # OLLAMA HEALTH
    # ---------------------------------------------------------

    def check_ollama(self):

        thread = threading.Thread(
            target=self._check_ollama_worker,
            daemon=True
        )

        thread.start()

    def _check_ollama_worker(self):

        try:

            request = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET"
            )

            with urllib.request.urlopen(
                request,
                timeout=5
            ) as response:

                if response.status == 200:

                    self.after(
                        0,
                        self._ollama_online
                    )

                    return

        except Exception:
            pass

        self.after(
            0,
            self._ollama_offline
        )

    def _ollama_online(self):

        self.status_vars["Ollama"].set(
            "● Ollama ONLINE"
        )

        self.ollama_badge.configure(
            fg="#4ade80"
        )

    def _ollama_offline(self):

        self.status_vars["Ollama"].set(
            "● Ollama OFFLINE"
        )

        self.ollama_badge.configure(
            fg="#f87171"
        )


if __name__ == "__main__":
    app = MemoLibDevApp()
    app.mainloop()
