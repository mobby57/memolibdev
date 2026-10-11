"""
MemoLibDev — Test CLI (déterministe, FakeProvider, sandbox éphémère)
====================================================================

Couvre les exigences du GO CLI :
  C1  READ_ONLY : aucune écriture, pas d'apply (final AWAIT_HUMAN/BLOCKED).
  C2  mission ambiguë -> QUESTION (clarification, pas de devinette).
  C3  réponse à la clarification -> reprise (contexte enrichi).
  C4  SUPERVISED_APPLY sans approbation -> AWAIT_HUMAN, aucune écriture.
  C5  SUPERVISED_APPLY avec approbation -> passe par D5.8/D5.9
      (APPLIED sur sandbox, jamais commit/push).
  C6  mission trop courte -> QUESTION.
  C7  la CLI ne fabrique jamais l'approbation (approval_fn réel requis).

Aucun vrai Ollama (FakeProvider déterministe). Aucun vrai stdin
(input_fn/approval_fn injectés). Aucun MemoLib réel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from project_target import ProjectTarget
from coder_authorization import HumanApproval, AuthorityLevel
from llm.ai_provider import FakeProvider
import memolibdev_cli as cli


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def make_lab() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-cli-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "cli@memolibdev.local")
    git(root, "config", "user.name", "cli")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    # Fichier avec 'version' pour matcher une mission claire.
    (root / "src" / "version.ts").write_text(
        "export const version = '1.0';\n", encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head = git(root, "rev-parse", "HEAD")
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    target = ProjectTarget(
        path=root, git_root=root, head=git(root, "rev-parse", "--short", "HEAD"),
        head_full=head, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET")
    return root, target


def never_input(prompt: str) -> str:
    raise AssertionError("input_fn ne devrait pas être appelé ici")


def never_approve(prompt: str):
    return None  # jamais d'approbation


def verify_pass_factory(tf: str):
    def verify(repo: Path):
        return ("version = '2.0'" in (repo / tf).read_text(encoding="utf-8"), "ok")
    return verify


CLEAR_MISSION = "mettre à jour la version 1.0 vers 2.0 dans version.ts"


class BootstrapCliTests(unittest.TestCase):
    """Tests unitaires du bootstrap CLI, sans fournisseur, réseau ni Git."""

    @staticmethod
    def _target():
        return SimpleNamespace(git_root=Path("C:/fake-project"), head="abc123")

    def test_read_only_skips_provider_and_reaches_orchestration(self):
        result = cli.CliResult("ANALYZED", "analyse terminée")
        with patch.dict(cli.os.environ, {}, clear=True), \
             patch.object(cli, "resolve_target", return_value=self._target()), \
             patch.object(cli, "_make_provider",
                          side_effect=AssertionError("provider interdit en READ_ONLY")), \
             patch.object(cli, "run_cli", return_value=result) as run:
            exit_code = cli.main([
                "--project", "C:/fake-project",
                "--mode", "READ_ONLY",
                "--mission", "analyse src/version.ts",
            ])

        self.assertEqual(exit_code, 0)
        self.assertIsNone(run.call_args.kwargs["provider"])
        self.assertEqual(run.call_args.kwargs["mode"], "READ_ONLY")

    def test_invalid_target_stops_before_provider_or_orchestration(self):
        with patch.dict(cli.os.environ, {}, clear=True), \
             patch.object(cli, "resolve_target",
                          side_effect=cli.ProjectTargetError("cible invalide")), \
             patch.object(cli, "_make_provider",
                          side_effect=AssertionError("provider ne doit pas être créé")), \
             patch.object(cli, "run_cli",
                          side_effect=AssertionError("orchestration interdite")):
            exit_code = cli.main([
                "--project", "C:/invalid",
                "--mode", "READ_ONLY",
                "--mission", "analyse src/version.ts",
            ])

        self.assertEqual(exit_code, 2)

    def test_non_read_only_modes_keep_provider_availability_gate(self):
        class UnavailableProvider:
            def __init__(self):
                self.available_checks = 0

            @property
            def available(self):
                self.available_checks += 1
                return False

        for mode in ("PROPOSE", "SANDBOX", "SUPERVISED_APPLY"):
            with self.subTest(mode=mode):
                provider = UnavailableProvider()
                with patch.dict(cli.os.environ, {}, clear=True), \
                     patch.object(cli, "resolve_target", return_value=self._target()), \
                     patch.object(cli, "_make_provider", return_value=provider) as make_provider, \
                     patch.object(cli, "run_cli",
                                  side_effect=AssertionError("orchestration interdite")):
                    exit_code = cli.main([
                        "--project", "C:/fake-project",
                        "--mode", mode,
                        "--mission", "analyse src/version.ts",
                    ])

                self.assertEqual(exit_code, 3)
                make_provider.assert_called_once()
                self.assertEqual(provider.available_checks, 1)

    def test_read_only_run_cli_forwards_no_provider_and_no_apply(self):
        report = SimpleNamespace(
            final_state="ANALYZED",
            reason="analyse terminée",
            proposal=None,
            committed=False,
            pushed=False,
        )
        verify = Mock(side_effect=AssertionError("verify ne doit pas être appelé"))

        with patch.object(cli, "_needs_clarification", return_value=None), \
             patch.object(cli, "run_from_mission",
                          return_value=SimpleNamespace(report=report)) as run:
            result = cli.run_cli(
                mission="analyse src/version.ts",
                target=self._target(),
                mode="READ_ONLY",
                model="fake",
                approver=None,
                provider=object(),
                verify=verify,
                input_fn=Mock(),
                approval_fn=Mock(),
                provider_timeout_s=None,
            )

        self.assertEqual(result.status, "ANALYZED")
        self.assertIsNone(run.call_args.kwargs["provider"])
        self.assertIsNone(run.call_args.kwargs["action"])
        self.assertIsNone(run.call_args.kwargs["human_approval"])
        verify.assert_not_called()


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST CLI (déterministe)")
    print("=" * 72)

    # ========================================================
    # C1 — READ_ONLY : aucune écriture, pas d'apply
    # ========================================================
    print("\n[C1] READ_ONLY -> pas d'apply, aucune écriture")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = git(root, "rev-parse", "HEAD")
        porcelain_before = git(root, "status", "--porcelain")
        res = cli.run_cli(
            mission=CLEAR_MISSION, target=target, mode="READ_ONLY",
            model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=verify_pass_factory(tf),
            input_fn=never_input, approval_fn=never_approve,
            provider_timeout_s=None)
        # READ_ONLY ne prend jamais la voie d'apply -> AWAIT_HUMAN attendu.
        ok("C1_pas_apply", res.status in ("AWAIT_HUMAN", "BLOCKED", "NO_PATCH_POSSIBLE"),
           f"status={res.status}")
        ok("C1_pas_committed",
           res.report is None or (not res.report.committed and not res.report.pushed), "")
        ok("C1_head_inchange", git(root, "rev-parse", "HEAD") == sha_before, "")
        ok("C1_working_tree_inchange",
           git(root, "status", "--porcelain") == porcelain_before, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C1b — READ_ONLY analyse sans planner ni proposition de diff
    # ========================================================
    print("\n[C1b] READ_ONLY -> ANALYZED, sans proposition")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = (root / tf).read_bytes()
        status_before = git(root, "status", "--porcelain")
        res = cli.run_cli(
            mission="Analyse le fichier src/version.ts et explique sa fonction",
            target=target, mode="READ_ONLY", model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=verify_pass_factory(tf),
            input_fn=never_input, approval_fn=never_approve,
            provider_timeout_s=None)
        ok("C1b_analyzed", res.status == "ANALYZED", f"status={res.status}")
        ok("C1b_no_proposal", res.report is not None and res.report.proposal is None, "")
        ok("C1b_file_unchanged", (root / tf).read_bytes() == sha_before, "")
        ok("C1b_working_tree_unchanged",
           git(root, "status", "--porcelain") == status_before, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C2 + C6 — mission ambiguë/courte -> QUESTION
    # ========================================================
    print("\n[C2+C6] Mission ambiguë -> QUESTION")
    root, target = make_lab()
    try:
        asked = {"q": None}
        def capture_input(prompt: str) -> str:
            asked["q"] = prompt
            return ""   # pas de réponse -> QUESTION
        res = cli.run_cli(
            mission="corrige le bug",          # vague, ne matche rien de fort
            target=target, mode="READ_ONLY", model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=lambda r: (True, "x"),
            input_fn=capture_input, approval_fn=never_approve,
            provider_timeout_s=None)
        ok("C2_question", res.status == "QUESTION", f"status={res.status}")
        ok("C2_question_posee", asked["q"] is not None and "préciser" in (asked["q"] or "").lower()
           or asked["q"] is not None,
           "une question a été posée")

        # C6 — mission trop courte
        res6 = cli.run_cli(
            mission="login", target=target, mode="READ_ONLY", model="fake",
            approver=None, provider=FakeProvider(scenario="happy"),
            verify=lambda r: (True, "x"),
            input_fn=lambda p: "", approval_fn=never_approve,
            provider_timeout_s=None)
        ok("C6_courte_question", res6.status == "QUESTION", f"status={res6.status}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C3 — réponse à la clarification -> reprise
    # ========================================================
    print("\n[C3] Réponse clarification -> reprise")
    root, target = make_lab()
    try:
        def answer_once(prompt: str) -> str:
            # Fournit une précision qui pointe vers version.ts.
            return "le fichier version.ts, remplacer version 1.0 par 2.0"
        res = cli.run_cli(
            mission="corrige le bug",          # ambigu au départ
            target=target, mode="READ_ONLY", model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=lambda r: (True, "x"),
            input_fn=answer_once, approval_fn=never_approve,
            provider_timeout_s=None)
        # Après enrichissement, la mission n'est plus ambiguë -> on passe
        # à l'exécution READ_ONLY (AWAIT_HUMAN/BLOCKED), plus de QUESTION.
        ok("C3_reprise", res.status != "QUESTION", f"status={res.status}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C4 — SUPERVISED_APPLY sans approbation -> AWAIT_HUMAN
    # ========================================================
    print("\n[C4] SUPERVISED_APPLY sans approbation -> AWAIT_HUMAN")
    root, target = make_lab()
    try:
        sha_before = git(root, "rev-parse", "HEAD")
        porcelain_before = git(root, "status", "--porcelain")
        res = cli.run_cli(
            mission=CLEAR_MISSION, target=target, mode="SUPERVISED_APPLY",
            model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=verify_pass_factory("src/version.ts"),
            input_fn=lambda p: "",
            approval_fn=lambda p: None,         # refuse l'approbation
            provider_timeout_s=None)
        ok("C4_await_human", res.status == "AWAIT_HUMAN", f"status={res.status}")
        ok("C4_head_inchange", git(root, "rev-parse", "HEAD") == sha_before, "")
        ok("C4_working_tree_inchange",
           git(root, "status", "--porcelain") == porcelain_before,
           "aucune écriture sans approbation")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C5 — SUPERVISED_APPLY avec approbation -> D5.8/D5.9 -> APPLIED
    # ========================================================
    print("\n[C5] SUPERVISED_APPLY avec approbation -> APPLIED (via D5.8/D5.9)")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_file_before = (root / tf).read_text(encoding="utf-8")
        head_before = git(root, "rev-parse", "HEAD")

        def real_approval(prompt: str):
            # Approbation EXPLICITE simulant une vraie saisie humaine.
            return HumanApproval(
                approved=True, approver="moro",
                approved_at=datetime.now(timezone.utc).isoformat(),
                authority_level=AuthorityLevel.L3_PROPOSE.value)

        res = cli.run_cli(
            mission=CLEAR_MISSION, target=target, mode="SUPERVISED_APPLY",
            model="fake", approver="moro",
            provider=FakeProvider(scenario="happy"),
            verify=verify_pass_factory(tf),
            input_fn=lambda p: "", approval_fn=real_approval,
            provider_timeout_s=None)
        ok("C5_applied", res.status == "APPLIED", f"status={res.status}")
        ok("C5_fichier_modifie",
           (root / tf).read_text(encoding="utf-8") != sha_file_before, "")
        ok("C5_pas_commit",
           res.report is not None and not res.report.committed
           and not res.report.pushed, "")
        # APPLIED != COMMITTED : HEAD inchangé.
        ok("C5_head_inchange", git(root, "rev-parse", "HEAD") == head_before,
           "APPLIED != COMMITTED")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # C7 — D5.8 obligatoire : approbation forgée côté LLM impossible.
    #      (Le provider ne peut pas produire d'approbation ; seul
    #       approval_fn le peut. On vérifie qu'un provider 'happy' sans
    #       approval_fn -> AWAIT_HUMAN.)
    # ========================================================
    print("\n[C7] Approbation jamais fabriquée par le provider")
    root, target = make_lab()
    try:
        res = cli.run_cli(
            mission=CLEAR_MISSION, target=target, mode="SUPERVISED_APPLY",
            model="fake", approver=None,
            provider=FakeProvider(scenario="happy"),
            verify=lambda r: (True, "x"),
            input_fn=lambda p: "",
            approval_fn=lambda p: None,         # aucune approbation
            provider_timeout_s=None)
        ok("C7_pas_apply_sans_humain", res.status == "AWAIT_HUMAN",
           f"status={res.status}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT CLI : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("CLI branchée sur run_from_mission. READ_ONLY par défaut.")
    print("Clarification interactive. D5.8/D5.9 obligatoires. "
          "Approbation jamais fabriquée. Aucun commit/push.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
