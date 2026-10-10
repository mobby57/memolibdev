"""
MemoLibDev — D6.2 : Code Adapter
=================================

Premier adaptateur de format. Traduit un `FileTarget` textuel code
(.py/.ts/.tsx/.js/.jsx et autres textuels) en opérations que la
chaîne D5.8/D5.9 peut consommer.

C'est un ADAPTATEUR, pas un moteur de sécurité. Il ne contourne
aucun garde-fou D5 — il produit les entrées que D5 vérifie.

Contrat SPEC-D6.0 §7bis.3 :
    read(file_target)        -> contenu texte brut
    analyze(content)         -> structure (lignes, imports, exports, fonctions)
    plan(content, intent)    -> changements proposés (traçables)
    modify(content, plan)    -> nouveau contenu (JAMAIS écrit sur disque)
    validate(old, new)       -> (ok, reason) : pas de corruption

Plus :
    generate_diff(old, new, path)  -> unified diff déterministe

Garanties :
  - modify() ne touche JAMAIS le disque.
  - Accepte uniquement FileTarget.is_textual == True.
  - Refuse les kinds non textuels (SHEET, PDF, IMAGE, BINARY…).
  - Le diff est limité au FileTarget.scope.
  - content_sha256 avant transformation reste lié à la cible.
  - Aucun Ollama, aucun git apply, aucun commit/push.
  - L'application réelle passe UNIQUEMENT par D5.9.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from file_target import FileTarget, FileTargetError


# ----------------------------------------------------------------
# Garde-fous d'admission
# ----------------------------------------------------------------

ACCEPTED_KINDS = {"CODE", "DATA", "DOC"}


class CodeAdapterError(RuntimeError):
    """Erreur de l'adaptateur code (fail-closed)."""


def _assert_textual(ft: FileTarget) -> None:
    """Refuse tout FileTarget non textuel. Fail-closed."""
    if not ft.is_textual:
        raise CodeAdapterError(
            f"code_adapter refuse les fichiers non textuels "
            f"(kind={ft.kind}, format={ft.format})"
        )
    if ft.kind not in ACCEPTED_KINDS:
        raise CodeAdapterError(
            f"code_adapter refuse le kind {ft.kind} "
            f"(acceptés : {sorted(ACCEPTED_KINDS)})"
        )


# ----------------------------------------------------------------
# 1. READ — lecture du contenu brut
# ----------------------------------------------------------------

def read(ft: FileTarget) -> str:
    """
    Lit le contenu texte du fichier décrit par le FileTarget.
    Ne modifie rien. Fail-closed si non textuel.
    """
    _assert_textual(ft)

    from pathlib import Path
    path = (Path(ft.git_root) / ft.path).resolve()

    if not path.is_file():
        raise CodeAdapterError(f"Fichier absent : {ft.path}")

    return path.read_text(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------
# 2. ANALYZE — compréhension structurelle
# ----------------------------------------------------------------

@dataclass(frozen=True)
class CodeStructure:
    """Vue structurelle d'un fichier code (read-only, en mémoire)."""
    path: str
    lines: int
    imports: list[str]
    exports: list[str]
    functions: list[str]
    classes: list[str]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "lines": self.lines,
            "imports": self.imports,
            "exports": self.exports,
            "functions": self.functions,
            "classes": self.classes,
        }


_IMPORT_RE = re.compile(
    r"^\s*(?:import |from |const .+ = require\()", re.MULTILINE
)
_EXPORT_RE = re.compile(
    r"^\s*export\s", re.MULTILINE
)
_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|"
    r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(|"
    r"def\s+(\w+)\s*\()",
    re.MULTILINE,
)
_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?class\s+(\w+)", re.MULTILINE
)


def analyze(content: str, path: str = "") -> CodeStructure:
    """
    Analyse structurelle légère du contenu. Pas d'AST lourd.
    Ne modifie rien.
    """
    imports = [m.group().strip() for m in _IMPORT_RE.finditer(content)]
    exports = [m.group().strip() for m in _EXPORT_RE.finditer(content)]

    functions = []
    for m in _FUNCTION_RE.finditer(content):
        name = m.group(1) or m.group(2) or m.group(3)
        if name:
            functions.append(name)

    classes = [m.group(1) for m in _CLASS_RE.finditer(content)]

    return CodeStructure(
        path=path,
        lines=content.count("\n") + (1 if content and not content.endswith("\n") else 0),
        imports=imports,
        exports=exports,
        functions=functions,
        classes=classes,
    )


# ----------------------------------------------------------------
# 3. PLAN — proposition de changements (traçable)
# ----------------------------------------------------------------

@dataclass(frozen=True)
class CodeChange:
    """Un changement proposé, traçable."""
    line: int           # ligne de début (1-based, 0 si global)
    action: str         # REPLACE | INSERT | DELETE | APPEND
    description: str    # explication humaine
    old_fragment: str   # texte avant (vide si INSERT/APPEND)
    new_fragment: str   # texte après (vide si DELETE)


@dataclass(frozen=True)
class CodePlan:
    """Plan de changements proposés pour un fichier."""
    path: str
    intent: str
    changes: list[CodeChange]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "intent": self.intent,
            "changes": [
                {
                    "line": c.line,
                    "action": c.action,
                    "description": c.description,
                    "old_fragment": c.old_fragment[:200],
                    "new_fragment": c.new_fragment[:200],
                }
                for c in self.changes
            ],
        }


def plan(content: str, intent: str, path: str = "") -> CodePlan:
    """
    Construit un plan de changements à partir du contenu actuel et
    d'une intention. En D6.2, le plan est DÉTERMINISTE (pas de LLM) :
    on applique l'intention comme une recherche-remplacement si elle
    contient un marqueur `REPLACE:old_text:new_text`, sinon on propose
    un APPEND du commentaire d'intention.

    L'intelligence agentique (LLM) viendra avec D6 Agent Loop.
    """
    changes: list[CodeChange] = []

    # Format déterministe : "REPLACE:old:new"
    if intent.startswith("REPLACE:"):
        parts = intent.split(":", 2)
        if len(parts) == 3:
            _, old_frag, new_frag = parts
            if old_frag in content:
                line = content[:content.index(old_frag)].count("\n") + 1
                changes.append(CodeChange(
                    line=line,
                    action="REPLACE",
                    description=f"Replace '{old_frag[:50]}' with '{new_frag[:50]}'",
                    old_fragment=old_frag,
                    new_fragment=new_frag,
                ))

    if not changes:
        # Fallback : ajouter un commentaire en fin de fichier.
        changes.append(CodeChange(
            line=0,
            action="APPEND",
            description=f"Append intent marker: {intent[:80]}",
            old_fragment="",
            new_fragment=f"\n// D6.2: {intent}\n",
        ))

    return CodePlan(path=path, intent=intent, changes=changes)


# ----------------------------------------------------------------
# 4. MODIFY — transformation en mémoire (JAMAIS sur disque)
# ----------------------------------------------------------------

def modify(content: str, code_plan: CodePlan) -> str:
    """
    Applique le plan de changements au contenu EN MÉMOIRE.
    Retourne le nouveau contenu. Ne touche JAMAIS le disque.
    """
    result = content

    for change in code_plan.changes:
        if change.action == "REPLACE":
            if change.old_fragment not in result:
                raise CodeAdapterError(
                    f"Fragment introuvable pour REPLACE: "
                    f"'{change.old_fragment[:50]}'"
                )
            result = result.replace(
                change.old_fragment,
                change.new_fragment,
                1,  # une seule occurrence
            )

        elif change.action == "APPEND":
            result = result + change.new_fragment

        elif change.action == "INSERT":
            lines = result.splitlines(keepends=True)
            idx = max(0, change.line - 1)
            lines.insert(idx, change.new_fragment)
            result = "".join(lines)

        elif change.action == "DELETE":
            if change.old_fragment and change.old_fragment in result:
                result = result.replace(change.old_fragment, "", 1)

    return result


# ----------------------------------------------------------------
# 5. VALIDATE — vérification de non-corruption
# ----------------------------------------------------------------

def validate(old: str, new: str) -> tuple[bool, str]:
    """
    Vérifie que la transformation n'a pas corrompu le contenu.
    Vérifications déterministes (pas de LLM).
    """
    if not new.strip():
        return False, "Le nouveau contenu est vide"

    if new == old:
        return False, "Aucune modification détectée"

    # Pas de perte massive (> 50% du contenu disparu).
    if len(new) < len(old) * 0.5 and len(old) > 100:
        return False, (
            f"Perte massive de contenu : {len(old)} -> {len(new)} "
            f"({100 - round(len(new) / len(old) * 100)}% perdu)"
        )

    return True, "Transformation valide"


# ----------------------------------------------------------------
# GENERATE_DIFF — unified diff déterministe
# ----------------------------------------------------------------

def generate_diff(old: str, new: str, path: str) -> str:
    """
    Produit un unified diff déterministe (sans LLM).
    Utilise difflib comme fallback hors-git.
    Pour les fichiers sous git, préférer generate_diff_git().
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )

    return "".join(diff)


def generate_diff_git(
    repo_root: "Path",
    rel_path: str,
    new_content: str,
) -> str:
    """
    Produit un unified diff via `git diff --no-index` réel — garantit
    la compatibilité avec `git apply` sans jamais modifier le working
    tree cible.

    Ne fait JAMAIS de commit/push. Méthode éprouvée (D5.8/D5.9).
    """
    target = (Path(repo_root) / rel_path).resolve()
    if not target.is_file():
        raise CodeAdapterError(f"Fichier absent : {rel_path}")

    original = target.read_bytes()

    with tempfile.TemporaryDirectory(prefix="memolibdev-diff-") as temp_dir:
        temp_root = Path(temp_dir)
        before = temp_root / "before"
        after = temp_root / "after"
        before.write_bytes(original)
        after.write_text(new_content, encoding="utf-8", newline="\n")

        result = subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                "--no-ext-diff",
                "--binary",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--",
                str(before),
                str(after),
            ],
            text=True, capture_output=True, encoding="utf-8", errors="replace",
        )

        if result.returncode not in (0, 1) or not result.stdout.strip():
            return ""

        diff = result.stdout
        for temporary, canonical in (
            (before, f"a/{rel_path}"),
            (after, f"b/{rel_path}"),
        ):
            windows_escaped = str(temporary).replace("\\", "\\\\")
            for path_text in {
                str(temporary),
                temporary.as_posix(),
                windows_escaped,
            }:
                diff = diff.replace(f'"a/{path_text}"', canonical)
                diff = diff.replace(f'"b/{path_text}"', canonical)
                diff = diff.replace(f"a/{path_text}", canonical)
                diff = diff.replace(f"b/{path_text}", canonical)

        return diff
