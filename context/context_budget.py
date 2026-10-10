"""
MemoLibDev — D6.0.1 : Context Budget
=====================================

Réduction DÉTERMINISTE et BORNÉE du contexte lorsqu'il est trop
volumineux pour être transmis en aval (un futur LLM, non branché ici).

Principe : on ne tronque jamais au hasard. On ordonne les fichiers par
pertinence (score fourni par la sélection), puis on remplit un budget
de caractères et un plafond de fichiers. Les éléments qui dépassent le
budget sont EXCLUS proprement, pas coupés en plein milieu.

Aucune écriture, aucun LLM, 100 % déterministe.
"""

from __future__ import annotations

from dataclasses import dataclass


# Plafonds par défaut (alignés sur l'esprit de decision_selector).
MAX_CONTEXT_CHARS = 8000
MAX_FILES = 12
MAX_FILE_CHARS = 2500        # borne par fichier


@dataclass(frozen=True)
class BudgetedItem:
    """Un fichier retenu dans le budget, avec son aperçu borné."""
    path: str
    score: int
    chars: int
    preview: str


@dataclass(frozen=True)
class BudgetResult:
    """Résultat de l'application du budget."""
    items: tuple[BudgetedItem, ...]
    total_chars: int
    included_count: int
    excluded_count: int
    reduced: bool            # True si une réduction a eu lieu


def apply_budget(
    candidates: list[dict],
    *,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    max_files: int = MAX_FILES,
    max_file_chars: int = MAX_FILE_CHARS,
) -> BudgetResult:
    """
    `candidates` : liste de dicts {path, score, preview}.
    Tri déterministe (-score, path), puis remplissage borné.

    Réduction = (fichiers exclus) OU (aperçus tronqués à max_file_chars).
    """
    ordered = sorted(
        candidates,
        key=lambda c: (-int(c.get("score", 0)), str(c.get("path", ""))),
    )

    items: list[BudgetedItem] = []
    total = 0
    excluded = 0
    reduced = False

    for c in ordered:
        if len(items) >= max_files:
            excluded += 1
            reduced = True
            continue

        preview = c.get("preview", "") or ""
        if len(preview) > max_file_chars:
            preview = preview[:max_file_chars]
            reduced = True

        chars = len(preview)
        if total + chars > max_context_chars:
            excluded += 1
            reduced = True
            continue

        items.append(BudgetedItem(
            path=str(c.get("path", "")),
            score=int(c.get("score", 0)),
            chars=chars,
            preview=preview,
        ))
        total += chars

    return BudgetResult(
        items=tuple(items),
        total_chars=total,
        included_count=len(items),
        excluded_count=excluded,
        reduced=reduced,
    )
