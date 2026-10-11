"""Tests ciblés du moteur documentaire technique V1."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from document_engine import (
    ENGINE_VERSION,
    EvidenceRef,
    HumanDecision,
    ProjectRef,
    TechnicalReport,
    TestResult,
    generate,
    load_registered_template,
    validate_report,
)


TEMPLATES = Path(__file__).parent / "templates"
SHA = "a" * 64


def report_fixture(**changes) -> TechnicalReport:
    report = TechnicalReport(
        report_id="report-001",
        mission_id="mission-001",
        generated_at="2026-10-11T00:00:00+00:00",
        project=ProjectRef(
            project_id="memolibdev",
            commit_sha="a" * 40,
            target_fingerprint=SHA,
        ),
        template_id="technical-report-v1",
        template_version="1.0",
        template_sha256=load_registered_template(
            "technical-report-v1", TEMPLATES
        ).template_sha256,
        engine_version=ENGINE_VERSION,
        evidence_refs=(
            EvidenceRef(
                ref_id="evidence-001",
                kind="TEST_LOG",
                source_ref="campaign/test.log",
                sha256=SHA,
                captured_at="2026-10-11T00:00:00+00:00",
            ),
        ),
        tests=(
            TestResult(
                name="intent-schema",
                command=("python", "-m", "unittest"),
                status="EXECUTED_PASS",
                returncode=0,
                evidence_refs=("evidence-001",),
            ),
        ),
        decisions=(
            HumanDecision(
                decision_id="decision-001",
                status="APPROVED",
                approver="reviewer-001",
                decided_at="2026-10-11T00:00:00+00:00",
                evidence_ref="evidence-001",
            ),
        ),
        validation_status="DRAFT",
        human_approval="APPROVED",
    )
    return replace(report, **changes)


class DocumentEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = load_registered_template("technical-report-v1", TEMPLATES)

    def test_three_formats_are_byte_deterministic(self) -> None:
        report = report_fixture()
        for format_name in ("md", "html", "txt"):
            first = generate(report, self.template, format_name)
            second = generate(report, self.template, format_name)
            self.assertEqual(first.content, second.content)
            self.assertEqual(first.content_sha256, second.content_sha256)

    def test_executed_pass_without_evidence_is_refused(self) -> None:
        report = report_fixture(tests=(
            replace(report_fixture().tests[0], evidence_refs=()),
        ))

        result = validate_report(report, self.template)

        self.assertFalse(result.ok)
        self.assertTrue(any("sans preuve" in error for error in result.errors))

    def test_absent_result_is_never_rendered_as_success(self) -> None:
        report = report_fixture(tests=(
            TestResult(
                name="not-run",
                command=(),
                status="NOT_EXECUTED",
                returncode=None,
                evidence_refs=(),
            ),
        ))

        document = generate(report, self.template, "txt")

        self.assertIn("NOT_EXECUTED", document.content)
        self.assertNotIn("EXECUTED_PASS", document.content)

    def test_invalid_sha_is_refused(self) -> None:
        evidence = replace(report_fixture().evidence_refs[0], sha256="bad")
        result = validate_report(
            report_fixture(evidence_refs=(evidence,)),
            self.template,
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("SHA-256" in error for error in result.errors))

    def test_human_approval_is_independent_from_validation(self) -> None:
        document = generate(
            report_fixture(human_approval="PENDING", decisions=()),
            self.template,
            "md",
        )

        self.assertEqual(document.report.validation_status, "VALID")
        self.assertEqual(document.report.human_approval, "PENDING")
        self.assertIn("Approbation humaine : PENDING", document.content)

    def test_html_escapes_untrusted_values(self) -> None:
        unsafe = replace(
            report_fixture().tests[0],
            name="<script>alert('x')</script>",
        )
        document = generate(
            report_fixture(tests=(unsafe,)),
            self.template,
            "html",
        )

        self.assertNotIn("<script>", document.content)
        self.assertIn("&lt;script&gt;", document.content)

    def test_unregistered_template_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "non enregistre"):
            load_registered_template("untrusted-template", TEMPLATES)

    def test_template_hash_is_stable(self) -> None:
        first = load_registered_template("technical-report-v1", TEMPLATES)
        second = load_registered_template("technical-report-v1", TEMPLATES)

        self.assertEqual(first.template_sha256, second.template_sha256)

    def test_contradictory_evidence_is_refused(self) -> None:
        first = report_fixture().evidence_refs[0]
        conflicting = replace(first, ref_id="evidence-002", sha256="b" * 64)
        result = validate_report(
            report_fixture(evidence_refs=(first, conflicting)),
            self.template,
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("contradictoire" in error for error in result.errors))

    def test_generator_never_reads_report_directory(self) -> None:
        report = report_fixture()

        document = generate(report, self.template, "txt")

        self.assertIn("report-001", document.content)

    def test_input_collections_are_defensively_immutable(self) -> None:
        evidence = [report_fixture().evidence_refs[0]]
        tests = [report_fixture().tests[0]]
        decisions = [report_fixture().decisions[0]]
        report = report_fixture(
            evidence_refs=evidence,
            tests=tests,
            decisions=decisions,
        )
        evidence.clear()
        tests.clear()
        decisions.clear()

        self.assertEqual(len(report.evidence_refs), 1)
        self.assertEqual(len(report.tests), 1)
        self.assertEqual(len(report.decisions), 1)

    def test_approved_status_requires_approved_decision(self) -> None:
        report = report_fixture(
            decisions=(),
            human_approval="APPROVED",
        )

        result = validate_report(report, self.template)

        self.assertFalse(result.ok)
        self.assertIn("approbation humaine sans decision APPROVED", result.errors)

    def test_non_draft_status_cannot_be_promoted(self) -> None:
        report = report_fixture(validation_status="REVIEW_REQUIRED")

        with self.assertRaisesRegex(ValueError, "DRAFT"):
            generate(report, self.template, "md")

    def test_text_is_normalized_and_cannot_add_rendered_lines(self) -> None:
        unsafe_test = replace(
            report_fixture().tests[0],
            name="e\u0301\r\n## faux titre | colonne",
        )
        report = report_fixture(tests=(unsafe_test,))

        markdown = generate(report, self.template, "md").content
        text = generate(report, self.template, "txt").content
        html = generate(report, self.template, "html").content

        self.assertNotIn("\r", markdown + text + html)
        self.assertIn("\\n", markdown)
        self.assertIn("é", markdown)
        self.assertIn("\\|", text)
        self.assertIn("\\#\\#", markdown)
        self.assertNotIn("<h2>faux titre", html)

    def test_duplicate_test_and_decision_identifiers_are_refused(self) -> None:
        base = report_fixture()
        duplicate_test = replace(base.tests[0], command=("python",))
        duplicate_decision = replace(base.decisions[0], approver="reviewer-002")
        report = report_fixture(
            tests=(base.tests[0], duplicate_test),
            decisions=(base.decisions[0], duplicate_decision),
        )

        result = validate_report(report, self.template)

        self.assertFalse(result.ok)
        self.assertTrue(any("nom de test duplique" in error for error in result.errors))
        self.assertTrue(any("decision_id duplique" in error for error in result.errors))

    def test_pending_approval_rejects_recorded_delivery_decision(self) -> None:
        result = validate_report(report_fixture(human_approval="PENDING"), self.template)

        self.assertFalse(result.ok)
        self.assertTrue(any("incompatible" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
