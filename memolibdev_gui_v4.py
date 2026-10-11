#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MemoLibDev GUI v4 - Autonome.
Cherche memolibdev_cli.py a cote de lui.
Verifie Ollama au demarrage.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

# --- Chemins relatifs (fonctionne dans un .exe PyInstaller) ---
def _base_dir() -> Path:
    """Dossier contenant les modules Python.
    En mode .exe : sys._MEIPASS (PyInstaller extrait les --add-data la).
    En mode .py : le dossier du script."""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = _base_dir()
CLI_PATH = BASE_DIR / "memolibdev_cli.py"


def find_cli_executable():
    """Trouve MemoLibDev-cli.exe.
    Cherche a cote de l'exe (sys.executable), puis dans _MEIPASS, puis a cote du script."""
    candidates = []
    if getattr(sys, "frozen", False):
        # A cote du .exe (cas normal : les deux .exe dans le meme dossier)
        candidates.append(Path(sys.executable).parent / "MemoLibDev-cli.exe")
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "MemoLibDev-cli.exe")
    candidates.append(Path(__file__).parent / "MemoLibDev-cli.exe")
    candidates.append(BASE_DIR / "MemoLibDev-cli.exe")

    for c in candidates:
        if c.is_file():
            return c
    return None


DEFAULT_MODEL = "memolibdev-qwen7b-16k:latest"
OLLAMA_URL = "http://localhost:11434"
CLI_TIMEOUT_SECONDS = 600
PROCESS_STOP_GRACE_SECONDS = 5


@dataclass(frozen=True)
class ProcessOutput:
    lines: list[str]
    timed_out: bool
    termination_confirmed: bool
    reader_error: str | None
    returncode: int | None


def _stop_process_tree(proc: subprocess.Popen) -> bool:
    """Arrête la CLI et ses descendants, jamais le service Ollama externe."""
    if proc.poll() is not None:
        return True

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PROCESS_STOP_GRACE_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                proc.kill()
        else:
            proc.terminate()
        proc.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
            proc.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
            return True
        except (OSError, subprocess.SubprocessError):
            return proc.poll() is not None


def _decode_cli_line(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace").rstrip("\r\n")


def _collect_process_output(
    proc: subprocess.Popen,
    timeout_seconds: float,
) -> ProcessOutput:
    """Lit stdout sans laisser une sortie silencieuse contourner le timeout."""
    output: queue.Queue[tuple[str, str | None]] = queue.Queue()
    lines: list[str] = []
    reader_error: str | None = None
    stdout_closed = False

    def read_stdout() -> None:
        try:
            if proc.stdout is None:
                output.put(("reader_error", "stdout indisponible"))
                return
            for raw in iter(proc.stdout.readline, b""):
                output.put(("line", _decode_cli_line(raw)))
        except (OSError, ValueError) as exc:
            output.put(("reader_error", str(exc)))
        finally:
            output.put(("eof", None))

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    termination_confirmed = True

    try:
        while proc.poll() is None or not stdout_closed:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                termination_confirmed = _stop_process_tree(proc)
                break
            try:
                kind, payload = output.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if kind == "line" and payload:
                lines.append(payload)
            elif kind == "reader_error":
                reader_error = payload
            elif kind == "eof":
                stdout_closed = True
    finally:
        if proc.poll() is None:
            termination_confirmed = _stop_process_tree(proc)
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass
        reader.join(timeout=PROCESS_STOP_GRACE_SECONDS)

    return ProcessOutput(
        lines=lines,
        timed_out=timed_out,
        termination_confirmed=termination_confirmed,
        reader_error=reader_error,
        returncode=proc.poll(),
    )

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG = "#0d1117"
CARD = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#58a6ff"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"
USER = "#1f6feb"


def check_ollama() -> tuple[bool, str]:
    """Verifie qu'Ollama repond sur localhost:11434."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            import json
            data = json.load(r)
            models = [m.get("name", "") for m in data.get("models", [])]
            return (True, f"Ollama OK ({len(models)} modele(s))")
    except Exception as e:
        return (False, f"Ollama injoignable : {e}")


def check_cli() -> tuple[bool, str]:
    if not CLI_PATH.is_file():
        return (False, f"memolibdev_cli.py introuvable dans {BASE_DIR}")
    return (True, f"CLI trouve : {CLI_PATH.name}")


class MemoLibDevApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MemoLibDev")
        self.geometry("960x820")
        self.minsize(720, 600)
        self.configure(fg_color=BG)

        self.update_idletasks()
        w, h = 960, 820
        x = (self.winfo_screenwidth() - w) // 2
        y = max(20, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.project_path = ctk.StringVar(value="(aucun projet)")
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        self.busy = False
        self.messages = []  # historique pour export
        self._closing = False
        self._ui_events: queue.Queue[tuple[object, tuple]] = queue.Queue()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen | None = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(100, self._check_env)
        self.after(50, self._drain_ui_events)

    def _post_ui(self, callback, *args) -> None:
        if not self._closing:
            self._ui_events.put((callback, args))

    def _drain_ui_events(self) -> None:
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except tk.TclError:
                return
        if not self._closing:
            try:
                self.after(50, self._drain_ui_events)
            except tk.TclError:
                pass

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        with self._process_lock:
            proc = self._active_process
        if proc is not None and proc.poll() is None:
            threading.Thread(
                target=_stop_process_tree,
                args=(proc,),
                daemon=False,
            ).start()
        self.destroy()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="  MemoLibDev",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=ACCENT).grid(row=0, column=0, sticky="w", padx=(16, 8), pady=16)

        self.project_label = ctk.CTkLabel(header, textvariable=self.project_path,
                                          font=ctk.CTkFont(size=10, slant="italic"),
                                          text_color=MUTED)
        self.project_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(header, text="Choisir projet",
                      command=self._choose_project,
                      width=140, height=34,
                      fg_color=CARD, hover_color="#21262d",
                      border_width=1, border_color=BORDER).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(header, text="Sauver log",
                      command=self._save_log,
                      width=100, height=34,
                      fg_color=CARD, hover_color="#21262d",
                      border_width=1, border_color=BORDER).grid(row=0, column=3, padx=(0, 16))

        self.chat = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self.chat.grid(row=1, column=0, sticky="nsew")
        self.chat.grid_columnconfigure(0, weight=1)

        sug = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        sug.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 4))

        for label in ["Decrire", "Erreurs", "Documenter", "Tests", "Securite"]:
            ctk.CTkButton(sug, text=label, command=lambda l=label: self._suggest(l),
                          width=100, height=30, fg_color=CARD,
                          hover_color="#21262d", border_width=1, border_color=BORDER
                          ).pack(side="left", padx=(0, 6))

        inp = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        inp.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 6))
        inp.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkTextbox(inp, height=70, fg_color=CARD,
                                     text_color=TEXT, wrap="word", border_width=0)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=10)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(inp, text="Envoyer", command=self._on_send,
                                       width=120, height=50,
                                       fg_color=ACCENT, hover_color="#79b8ff",
                                       text_color="#0d1117")
        self.send_btn.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.status = ctk.CTkLabel(self, text="Prêt.", text_color=MUTED)
        self.status.grid(row=4, column=0, sticky="w", padx=20, pady=(0, 8))

    def _check_env(self):
        cli_ok, cli_msg = check_cli()
        ollama_ok, ollama_msg = check_ollama()

        if not cli_ok:
            self._assistant(f"ERREUR : {cli_msg}\n\nPlacez ce programme a cote de memolibdev_cli.py.")
            self.status.configure(text="ERREUR : CLI introuvable")
            return
        if not ollama_ok:
            self._assistant(
                "Ollama n'est pas accessible.\n\n"
                "Pour utiliser MemoLibDev, vous devez :\n"
                "1. Telecharger Ollama sur https://ollama.com/download\n"
                "2. L'installer\n"
                "3. Lancer Ollama\n"
                "4. Telecharger un modele : ollama pull qwen2.5-coder:7b\n\n"
                "Puis relancez MemoLibDev.")
            self.status.configure(text="Ollama non disponible")
            return

        self._assistant(
            f"Bonjour.\n\n{cli_msg}\n{ollama_msg}\n\n"
            "Choisissez un projet (bouton en haut a droite), "
            "puis decrivez ce que vous voulez faire en francais.\n\n"
            "Je ne modifie rien sans votre accord.")

    def _choose_project(self):
        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")

    def _suggest(self, label):
        m = {"Decrire": "Decris la structure du projet",
             "Erreurs": "Analyse le code et signale les erreurs",
             "Documenter": "Documente les fonctions principales",
             "Tests": "Identifie les tests et ce qu'ils verifient",
             "Securite": "Cherche les patterns de securite sensibles"}
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", m.get(label, label))

    def _on_enter(self, event):
        if event.state & 0x0001:
            return None
        self._on_send()
        return "break"

    def _on_send(self):
        if self.busy:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")

        proj = self.project_path.get()
        if not proj or proj.startswith("("):
            self._assistant("Aucun projet selectionne. Cliquez sur 'Choisir projet'.")
            return

        self._user(text)
        self._run(proj, text)

    def _user(self, t):
        self._bubble(t, "user")

    def _assistant(self, t):
        self._bubble(t, "assistant")

    def _system(self, t):
        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(f, text=t, text_color=MUTED,
                     font=ctk.CTkFont(size=10, slant="italic"),
                     anchor="w", justify="left", wraplength=800).pack(fill="x")

    def _bubble(self, text, role):
        f = ctk.CTkFrame(self.chat, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=8)

        if role == "user":
            bg, fg, anchor, padx, author = USER, "#ffffff", "e", (60, 0), "Vous"
        else:
            bg, fg, anchor, padx, author = CARD, TEXT, "w", (0, 60), "MemoLibDev"

        b = ctk.CTkFrame(f, fg_color=bg, corner_radius=14)
        b.pack(anchor=anchor, padx=padx)

        ctk.CTkLabel(b, text=author, text_color=ACCENT if role == "assistant" else "#ffffff",
                     font=ctk.CTkFont(size=10, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=14, pady=(10, 2))

        ctk.CTkLabel(b, text=text, text_color=fg,
                     font=ctk.CTkFont(size=12), anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=14, pady=(0, 10))

        self.messages.append(f"[{author}] {text}")
        self.after(80, self._scroll)

    def _scroll(self):
        try:
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _save_log(self):
        from tkinter import filedialog
        import datetime
        p = filedialog.asksaveasfilename(
            title="Sauver le log",
            defaultextension=".txt",
            initialfile=f"memolibdev_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Texte", "*.txt"), ("Tous", "*.*")],
        )
        if not p:
            return
        try:
            Path(p).write_text("\n".join(self.messages), encoding="utf-8")
            self._system(f"Log sauve : {p}")
        except Exception as e:
            self._assistant(f"Erreur sauvegarde : {e}")

    def _run(self, project, mission):
        self.busy = True
        self.send_btn.configure(state="disabled")
        self.status.configure(text="En cours...")

        def worker():
            proc = None
            completion_status = "Pret."
            # Trouver le CLI : MemoLibDev-cli.exe a cote, sinon memolibdev_cli.py
            cli_exe = find_cli_executable()
            cli_py = BASE_DIR / "memolibdev_cli.py"

            env = os.environ.copy()
            env["MEMOLIBDEV_TARGET"] = project
            env["PYTHONIOENCODING"] = "utf-8"

            if cli_exe is not None:
                cmd = [str(cli_exe)]
                self._post_ui(self._system, f"CLI : {cli_exe}")
            elif cli_py.is_file():
                cmd = [sys.executable, str(cli_py)]
                self._post_ui(self._system, f"CLI (python) : {cli_py}")
            else:
                completion_status = "Erreur : CLI introuvable."
                self._post_ui(
                    self._assistant,
                    f"CLI introuvable. Cherche dans :\n"
                    f"  {Path(sys.executable).parent}\n"
                    f"  {BASE_DIR}",
                )
                self._post_ui(self._done, completion_status)
                return

            # Detecter automatiquement le mode selon la mission
            mission_lower = mission.lower()
            keywords_analyse = (
                "decris", "décris", "analyse", "explique", "liste",
                "documente", "cherche", "trouve", "signale", "identifie",
                "verifie", "vérifie", "resume", "résume", "presente",
                "présente", "explore", "inspecte", "comprends",
            )
            if any(k in mission_lower for k in keywords_analyse):
                mode = "READ_ONLY"
            else:
                mode = "PROPOSE"

            self._post_ui(self._system, f"Mode : {mode}")

            cmd += [
                "--mission", mission,
                "--mode", mode,
                "--model", self.model_var.get().strip(),
                "--timeout", "300",
            ]

            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt":
                    creationflags |= getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                    )
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(BASE_DIR),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                with self._process_lock:
                    self._active_process = proc

                output = _collect_process_output(proc, CLI_TIMEOUT_SECONDS)
                if output.lines:
                    self._post_ui(self._assistant, "\n".join(output.lines))
                if output.reader_error:
                    self._post_ui(
                        self._assistant,
                        f"Lecture CLI : {output.reader_error}",
                    )
                if output.timed_out:
                    completion_status = "Timeout : CLI arretee."
                    message = (
                        "Delai global depasse. La CLI et ses processus "
                        "enfants ont ete arretes."
                    )
                    if not output.termination_confirmed:
                        message = (
                            "Delai global depasse ; arret du processus "
                            "non confirme."
                        )
                    self._post_ui(self._assistant, message)
                elif output.returncode:
                    completion_status = (
                        f"CLI terminee avec le code {output.returncode}."
                    )
                    self._post_ui(self._assistant, completion_status)
            except OSError as exc:
                completion_status = "Erreur de lancement CLI."
                self._post_ui(
                    self._assistant,
                    f"Erreur de lancement : {type(exc).__name__}: {exc}",
                )
            except Exception as exc:
                completion_status = "Erreur inattendue de supervision."
                self._post_ui(
                    self._assistant,
                    f"Erreur : {type(exc).__name__}: {exc}",
                )
            finally:
                if proc is not None and proc.poll() is None:
                    _stop_process_tree(proc)
                with self._process_lock:
                    if self._active_process is proc:
                        self._active_process = None
                self._post_ui(self._done, completion_status)

        threading.Thread(target=worker, daemon=True).start()

    def _display(self, raw):
        if not raw.strip():
            self._assistant("(aucune sortie)")
            return
        for line in raw.splitlines():
            if line.strip():
                self._assistant(line)

    def _done(self, status_text="Pret."):
        self.busy = False
        self.send_btn.configure(state="normal")
        self.status.configure(text=status_text)


def main():
    app = MemoLibDevApp()
    app.mainloop()


if __name__ == "__main__":
    main()
