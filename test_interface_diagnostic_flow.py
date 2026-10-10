from __future__ import annotations

import json
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from interface.app import MemoLibDevApp
from interface.diagnostics import ollama_failure, successful_step


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class FakeBadge:
    def __init__(self) -> None:
        self.options: dict[str, str] = {}

    def configure(self, **options: str) -> None:
        self.options.update(options)


class FakeApp:
    def __init__(self) -> None:
        self.status_vars = {
            "Inspector": FakeVariable(),
            "Ollama": FakeVariable(),
        }
        self.ollama_badge = FakeBadge()
        self.system_messages: list[str] = []
        self.agent_answers: list[str] = []
        self.inspection_error: Exception | None = None
        self.web_report = {"success": True, "sources": []}
        self.ollama_diagnostic = successful_step("Génération Ollama", 0.5)

    def after(self, _delay: int, callback) -> None:
        callback()

    def _append_system(self, message: str) -> None:
        self.system_messages.append(message)

    def _agent_response(self, answer: str) -> None:
        self.agent_answers.append(answer)

    def _candidate_files(self, _request: str) -> list[Path]:
        return [Path("README.md")]

    def _run_inspector(self, _paths: list[Path]) -> dict:
        if self.inspection_error is not None:
            raise self.inspection_error
        return {"files": [{"requested_path": "README.md"}]}

    def _build_context(self, _files: list[dict]) -> str:
        return "contexte simulé"

    def _run_web_research(self, _request: str) -> dict:
        return self.web_report

    def _build_web_context(self, _report: dict) -> str:
        return "web simulé"

    def _ask_ollama(self, *_args, **_kwargs):
        return self.ollama_diagnostic

    def _show_diagnostic_failure(self, diagnostic, diagnostics) -> None:
        MemoLibDevApp._show_diagnostic_failure(self, diagnostic, diagnostics)

    def run(self) -> None:
        MemoLibDevApp._inspect_and_ask(self, "diagnostic simulé")


class OllamaHarness:
    def __init__(self) -> None:
        self.answers: list[str] = []

    def after(self, _delay: int, callback) -> None:
        callback()

    def _agent_response(self, answer: str) -> None:
        self.answers.append(answer)


class InterfaceDiagnosticFlowTests(unittest.TestCase):
    def test_complete_success_displays_all_step_durations(self) -> None:
        app = FakeApp()

        app.run()

        summary = app.status_vars["Inspector"].value
        self.assertIn("Sélection:", summary)
        self.assertIn("Inspection:", summary)
        self.assertIn("Recherche Web:", summary)
        self.assertIn("Génération Ollama:", summary)
        self.assertEqual(app.system_messages, [])

    def test_inspection_timeout_stops_before_ollama(self) -> None:
        app = FakeApp()
        app.inspection_error = subprocess.TimeoutExpired(
            ["python", "inspector.py"],
            120,
        )

        app.run()

        message = app.system_messages[-1]
        self.assertIn("INSPECTION_TIMEOUT", message)
        self.assertIn("limite configurée : 120s", message)
        self.assertNotIn("Génération Ollama:", message)

    def test_web_degradation_is_reported_without_false_success(self) -> None:
        app = FakeApp()
        app.web_report = {
            "success": True,
            "sources": [{"error": "network detail that must not be shown"}],
        }

        app.run()

        self.assertIn("WEB_RESEARCH_FAILED", app.system_messages[-1])
        self.assertNotIn(
            "network detail that must not be shown",
            app.system_messages[-1],
        )

    def test_ollama_timeout_stops_with_measured_limit(self) -> None:
        app = FakeApp()
        app.ollama_diagnostic = ollama_failure(
            180.25,
            TimeoutError("timed out"),
            180,
        )

        app.run()

        message = app.system_messages[-1]
        self.assertIn("OLLAMA_TIMEOUT", message)
        self.assertIn("limite configurée : 180s", message)
        self.assertNotIn("terminé", message)

    def test_ollama_connection_error_is_not_timeout(self) -> None:
        app = FakeApp()
        app.ollama_diagnostic = ollama_failure(
            0.1,
            urllib.error.URLError(ConnectionRefusedError("refused")),
            180,
        )

        app.run()

        message = app.system_messages[-1]
        self.assertIn("OLLAMA_CONNECTION_ERROR", message)
        self.assertNotIn("OLLAMA_TIMEOUT", message)
        self.assertNotIn("limite configurée", message)

    def test_ollama_other_error_is_not_timeout(self) -> None:
        app = FakeApp()
        app.ollama_diagnostic = ollama_failure(
            0.1,
            ValueError("sensitive error detail"),
            180,
        )

        app.run()

        message = app.system_messages[-1]
        self.assertIn("OLLAMA_ERROR", message)
        self.assertNotIn("sensitive error detail", message)
        self.assertNotIn("OLLAMA_TIMEOUT", message)

    def test_ask_ollama_classifies_timeout_without_network(self) -> None:
        harness = OllamaHarness()

        with patch(
            "interface.app.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            diagnostic = MemoLibDevApp._ask_ollama(
                harness,
                "requête simulée",
                "contexte simulé",
                [],
            )

        self.assertEqual(diagnostic.error_code, "OLLAMA_TIMEOUT")
        self.assertEqual(diagnostic.timeout_s, 180)

    def test_ask_ollama_success_uses_mocked_response(self) -> None:
        harness = OllamaHarness()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"response": "réponse simulée"}).encode()

        with patch(
            "interface.app.urllib.request.urlopen",
            return_value=Response(),
        ):
            diagnostic = MemoLibDevApp._ask_ollama(
                harness,
                "requête simulée",
                "contexte simulé",
                [],
            )

        self.assertFalse(diagnostic.failed)
        self.assertEqual(harness.answers, ["réponse simulée"])


if __name__ == "__main__":
    unittest.main()
