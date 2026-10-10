"""Tests unitaires sans Ollama pour l'evidence CREATE et son rollback."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from create_apply import apply_create
from create_authorization import (
    CreateAuthorizationError,
    build_create_approval,
    verify_create_approval,
)
from create_proof import (
    capture_absence_evidence,
    validate_absence_evidence,
    validate_rollback_absence_proof,
)
from create_target import CreateTargetError, resolve_create_target


class CreateProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="memolibdev-create-")
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@local"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "test"],
            check=True,
        )
        (self.root / "README.md").write_text("# CREATE test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "baseline"],
            check=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_absence_evidence_is_bound_to_target_and_head(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        evidence = capture_absence_evidence(target)

        self.assertTrue(validate_absence_evidence(target, evidence)[0])
        self.assertEqual(evidence.target_path, "report.md")
        self.assertEqual(len(evidence.evidence_sha256), 64)

    def test_approval_is_bound_to_absence_evidence(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        evidence = capture_absence_evidence(target)
        approval = build_create_approval(
            "test",
            target.rel_path,
            "# Report\n",
            evidence.evidence_sha256,
        )

        verify_create_approval(
            approval,
            target.rel_path,
            "# Report\n",
            evidence.evidence_sha256,
        )
        with self.assertRaises(CreateAuthorizationError):
            verify_create_approval(
                approval,
                target.rel_path,
                "# Report\n",
                "0" * 64,
            )

    def test_file_appearing_before_apply_is_blocked_without_overwrite(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        evidence = capture_absence_evidence(target)
        target.abs_path.write_text("external content\n", encoding="utf-8")

        result = apply_create(
            target,
            "# Proposed\n",
            lambda _: (True, "should not run"),
            evidence,
        )

        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(target.abs_path.read_text(encoding="utf-8"), "external content\n")

    def test_expired_absence_evidence_is_blocked(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        captured_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        evidence = capture_absence_evidence(
            target,
            ttl_seconds=1,
            now=captured_at,
        )

        result = apply_create(
            target,
            "# Proposed\n",
            lambda _: (True, "should not run"),
            evidence,
        )

        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(target.abs_path.exists())

    def test_verify_failure_removes_file_and_emits_rollback_proof(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        evidence = capture_absence_evidence(target)

        result = apply_create(
            target,
            "# Proposed\n",
            lambda _: (False, "verification volontairement refusee"),
            evidence,
        )

        self.assertEqual(result.status, "ROLLED_BACK")
        self.assertTrue(result.rolled_back)
        self.assertFalse(target.abs_path.exists())
        self.assertEqual(result.absence_evidence_sha256, evidence.evidence_sha256)
        self.assertIsNotNone(result.rollback_proof_sha256)
        self.assertEqual(len(result.rollback_proof_sha256 or ""), 64)
        self.assertIsNotNone(result.rollback_proof)
        self.assertTrue(
            validate_rollback_absence_proof(
                target,
                evidence,
                result.rollback_proof,
            )[0]
        )
        status = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(status.stdout, "")

    def test_rollback_refuses_to_delete_an_externally_modified_file(self) -> None:
        target = resolve_create_target(self.root, "report.md")
        evidence = capture_absence_evidence(target)

        def modify_then_fail(path: Path) -> tuple[bool, str]:
            path.write_text("external content\n", encoding="utf-8")
            return False, "verification volontairement refusee"

        result = apply_create(
            target,
            "# Proposed\n",
            modify_then_fail,
            evidence,
        )

        self.assertEqual(result.status, "ROLLBACK_FAILED")
        self.assertFalse(result.rolled_back)
        self.assertEqual(target.abs_path.read_text(encoding="utf-8"), "external content\n")

    def test_parent_directory_must_exist(self) -> None:
        with self.assertRaises(CreateTargetError):
            resolve_create_target(self.root, "missing/report.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
