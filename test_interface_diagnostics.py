from __future__ import annotations

import socket
import subprocess
import unittest
import urllib.error

from interface.diagnostics import (
    inspection_failure,
    ollama_failure,
    successful_step,
    timing_summary,
    web_research_diagnostic,
)


class InterfaceDiagnosticsTests(unittest.TestCase):
    def test_inspection_timeout_keeps_duration_and_limit(self) -> None:
        error = subprocess.TimeoutExpired(["python", "inspector.py"], 120)

        diagnostic = inspection_failure(120.25, error, 120)

        self.assertEqual(diagnostic.error_code, "INSPECTION_TIMEOUT")
        self.assertEqual(diagnostic.duration_s, 120.25)
        self.assertEqual(diagnostic.timeout_s, 120)
        self.assertEqual(diagnostic.exception_type, "TimeoutExpired")

    def test_ollama_timeout_is_not_a_connection_error(self) -> None:
        diagnostic = ollama_failure(180.5, TimeoutError("timed out"), 180)

        self.assertEqual(diagnostic.error_code, "OLLAMA_TIMEOUT")
        self.assertEqual(diagnostic.timeout_s, 180)
        self.assertIn("durée mesurée : 180.50s", diagnostic.user_message())

    def test_ollama_connection_error_is_distinct(self) -> None:
        error = urllib.error.URLError(ConnectionRefusedError("refused"))

        diagnostic = ollama_failure(0.25, error, 180)

        self.assertEqual(diagnostic.error_code, "OLLAMA_CONNECTION_ERROR")
        self.assertIsNone(diagnostic.timeout_s)

    def test_ollama_other_error_is_not_mislabeled(self) -> None:
        diagnostic = ollama_failure(0.1, ValueError("invalid response"), 180)

        self.assertEqual(diagnostic.error_code, "OLLAMA_ERROR")

    def test_user_message_does_not_expose_exception_content(self) -> None:
        secret = "api_key=do-not-display"
        diagnostic = ollama_failure(0.1, ValueError(secret), 180)

        self.assertNotIn(secret, diagnostic.user_message())
        self.assertIn("exception : ValueError", diagnostic.user_message())

    def test_web_failure_is_degraded(self) -> None:
        diagnostic = web_research_diagnostic(
            15.0,
            {
                "success": True,
                "sources": [{"error": "network unavailable"}],
            },
        )

        self.assertTrue(diagnostic.degraded)
        self.assertEqual(diagnostic.error_code, "WEB_RESEARCH_FAILED")

    def test_success_summary_contains_no_exception_message(self) -> None:
        diagnostics = [
            successful_step("Sélection", 0.01),
            successful_step("Inspection", 1.5),
        ]

        self.assertEqual(
            timing_summary(diagnostics),
            "Sélection: 0.01s | Inspection: 1.50s",
        )

    def test_socket_timeout_is_classified_as_timeout(self) -> None:
        diagnostic = ollama_failure(3.0, socket.timeout("timed out"), 180)

        self.assertEqual(diagnostic.error_code, "OLLAMA_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
