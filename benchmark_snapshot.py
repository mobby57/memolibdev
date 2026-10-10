"""
MemoLibDev — Harnais de benchmark reproductible (Option B : clone figé)
=======================================================================

PROBLÈME (diagnostiqué) : le benchmark passait par `build_mission_context`
-> `inspect_target`, qui scanne le WORKING TREE VIVANT de la cible. Des
fichiers transitoires (_archive/, bin/, obj/, .vscode/…) pouvaient donc
entrer dans le contexte et rendre la mesure NON reproductible, alors même
que HEAD git était identique.

SOLUTION (Option B, harnais uniquement) : avant de mesurer, on crée un
CLONE FIGÉ de la cible AU HEAD demandé. Le clone ne contient QUE l'état
versionné (les fichiers non suivis — _archive/bin/obj — ne sont pas
clonés). Le benchmark exécute ensuite le VRAI `build_mission_context` sur
ce clone. Résultat : même HEAD -> même snapshot -> même contexte.

Garanties :
  - le MOTEUR n'est pas modifié : on réutilise build_mission_context /
    inspect_target / 5A / 5.2 / 5.3 tels quels ;
  - `project_inspector` n'est pas modifié ;
  - le working tree RÉEL de la cible ne participe jamais au benchmark ;
  - clone créé à partir du HEAD explicite (git clone + checkout detaché) ;
  - clone supprimé après usage (contexte manager).

Ce module appartient au HARNAIS DE MESURE, pas au moteur. Il n'applique
rien, ne commit rien, ne touche jamais la cible réelle.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile

from project_target import ProjectTarget


def _rmtree_force(path: Path) -> None:
    """
    Supprime un arbre, y compris les fichiers en LECTURE SEULE (Windows :
    git clone --local crée des objets .git read-only que shutil.rmtree ne
    peut pas effacer sans retirer l'attribut au préalable).
    """
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=_onerror)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          text=True, capture_output=True,
                          encoding="utf-8", errors="replace")


def _fingerprint(git_root: str, branch: str, head: str) -> str:
    raw = f"{git_root}|{branch}|{head}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@contextmanager
def frozen_clone(source: ProjectTarget, head: str | None = None):
    """
    Crée un CLONE FIGÉ de `source` au HEAD demandé (défaut : HEAD courant
    de la source) et yield un `ProjectTarget` pointant sur ce clone.

    Le clone ne contient QUE l'arbre versionné du commit : les fichiers
    non suivis (bin/, obj/, _archive/, .vscode/ non commités…) sont
    absents par construction. Le clone est détruit en sortie.

    Ne modifie JAMAIS la source. Lecture seule sur la source (git clone).
    """
    src_root = source.git_root.resolve()
    target_head = head or source.head_full

    tmp = Path(tempfile.mkdtemp(prefix="memolibdev-snapshot-")).resolve()
    clone_dir = tmp / src_root.name
    try:
        # Clone local (lecture seule de la source). --no-checkout puis
        # checkout détaché au HEAD exact : l'arbre reflète précisément le
        # commit, sans fichiers non suivis.
        r = subprocess.run(
            ["git", "clone", "--quiet", "--local", "--no-checkout",
             str(src_root), str(clone_dir)],
            text=True, capture_output=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"git clone a échoué : {r.stderr.strip()}")

        co = _git(clone_dir, "checkout", "--quiet", "--detach", target_head)
        if co.returncode != 0:
            raise RuntimeError(f"git checkout {target_head} a échoué : "
                               f"{co.stderr.strip()}")

        head_full = _git(clone_dir, "rev-parse", "HEAD").stdout.strip()
        head_short = _git(clone_dir, "rev-parse", "--short", "HEAD").stdout.strip()
        # Branche : detached -> on garde le nom logique de la source pour
        # la cohérence du fingerprint fonctionnel ; sinon 'HEAD'.
        branch = source.branch or "HEAD"
        fp = _fingerprint(str(clone_dir), branch, head_full)

        snapshot_target = ProjectTarget(
            path=clone_dir, git_root=clone_dir,
            head=head_short, head_full=head_full,
            branch=branch, fingerprint=fp, env_var=source.env_var)

        yield snapshot_target
    finally:
        _rmtree_force(tmp)


def snapshot_inventory(target: ProjectTarget) -> list[str]:
    """
    Liste déterministe (triée) des chemins inspectables du snapshot, via
    le VRAI inspecteur du moteur (inspect_target). Sert aux tests de
    reproductibilité. Lecture seule.
    """
    from context.project_inspector import inspect_target
    insp = inspect_target(target)
    return sorted(f.path for f in insp.files)
