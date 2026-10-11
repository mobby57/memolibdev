"""Tests sans GUI ni Ollama pour la supervision de sous-processus."""

from __future__ import annotations
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from memolibdev_gui_v4 import MemoLibDevApp, _collect_process_output


def _child(code: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


class GuiProcessSupervisionTests(unittest.TestCase):
    def _headless_app(self):
        app = object.__new__(MemoLibDevApp)
        events: list[tuple[str, str]] = []
        completed = threading.Event()
        completion_status: list[str] = []

        class Widget:
            def configure(self, **_kwargs) -> None:
                pass

        class Model:
            def get(self) -> str:
                return "fake-model"

        def done(status_text="Pret.") -> None:
            completion_status.append(status_text)
            completed.set()

        app.busy = False
        app.send_btn = Widget()
        app.status = Widget()
        app.model_var = Model()
        app._process_lock = threading.Lock()
        app._active_process = None
        app._post_ui = lambda callback, *args: callback(*args)
        app._system = lambda message: events.append(("system", message))
        app._assistant = lambda message: events.append(("assistant", message))
        app._done = done

        return app, events, completed, completion_status

    def _run_headless_worker(
        self,
        mission: str,
        child_code: str,
        timeout_seconds: float = 2,
    ):
        app, events, completed, completion_status = self._headless_app()
        started: list[subprocess.Popen] = []
        commands: list[list[str]] = []
        real_popen = subprocess.Popen
        fake_cli = Path("C:/isolated/MemoLibDev-cli.exe")

        def launch_child(command, **kwargs):
            commands.append(command)
            proc = real_popen(
                [sys.executable, "-c", child_code],
                **kwargs,
            )
            started.append(proc)
            return proc

        with patch(
            "memolibdev_gui_v4.find_cli_executable",
            return_value=fake_cli,
        ), patch(
            "memolibdev_gui_v4.subprocess.Popen",
            side_effect=launch_child,
        ), patch(
            "memolibdev_gui_v4.CLI_TIMEOUT_SECONDS",
            timeout_seconds,
        ):
            app._run(str(Path.cwd()), mission)
            self.assertTrue(completed.wait(timeout=5), "worker non terminé")

        return app, events, completion_status, commands, started

    def test_silent_process_times_out_and_is_stopped(self) -> None:
        proc = _child("import time; time.sleep(30)")

        output = _collect_process_output(proc, timeout_seconds=0.2)

        self.assertTrue(output.timed_out)
        self.assertTrue(output.termination_confirmed)
        self.assertIsNotNone(output.returncode)

    def test_normal_output_is_collected(self) -> None:
        proc = _child("print('alpha'); print('beta')")

        output = _collect_process_output(proc, timeout_seconds=2)

        self.assertFalse(output.timed_out)
        self.assertEqual(output.returncode, 0)
        self.assertEqual(output.lines, ["alpha", "beta"])

    def test_nonzero_exit_is_reported(self) -> None:
        proc = _child("import sys; print('failure'); sys.exit(7)")

        output = _collect_process_output(proc, timeout_seconds=2)

        self.assertFalse(output.timed_out)
        self.assertEqual(output.returncode, 7)
        self.assertEqual(output.lines, ["failure"])

    def test_worker_uses_cli_executable_and_read_only_for_analysis(self) -> None:
        app, events, statuses, commands, started = self._run_headless_worker(
            "Analyse le projet et explique sa structure",
            "print('analyse terminee')",
        )

        self.assertFalse(app.busy)
        self.assertEqual(statuses, ["Pret."])
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], "C:\\isolated\\MemoLibDev-cli.exe")
        self.assertEqual(commands[0][commands[0].index("--mode") + 1], "READ_ONLY")
        self.assertIn(("system", "Mode : READ_ONLY"), events)
        self.assertIn(("assistant", "analyse terminee"), events)
        self.assertIsNone(app._active_process)
        self.assertIsNotNone(started[0].poll())

    def test_worker_uses_propose_for_change_request(self) -> None:
        _app, events, statuses, commands, started = self._run_headless_worker(
            "Corrige la version du projet",
            "print('proposition prete')",
        )

        self.assertEqual(statuses, ["Pret."])
        self.assertEqual(commands[0][commands[0].index("--mode") + 1], "PROPOSE")
        self.assertIn(("system", "Mode : PROPOSE"), events)
        self.assertIn(("assistant", "proposition prete"), events)
        self.assertIsNotNone(started[0].poll())

    def test_worker_timeout_stops_fake_cli(self) -> None:
        app, events, statuses, _commands, started = self._run_headless_worker(
            "Analyse le projet",
            "import time; time.sleep(30)",
            timeout_seconds=0.2,
        )

        self.assertEqual(statuses, ["Timeout : CLI arretee."])
        self.assertTrue(any(
            kind == "assistant" and "Delai global depasse" in message
            for kind, message in events
        ))
        self.assertIsNone(app._active_process)
        self.assertIsNotNone(started[0].poll())

    def test_window_close_stops_active_fake_cli(self) -> None:
        app = object.__new__(MemoLibDevApp)
        proc = _child("import time; time.sleep(30)")
        destroyed = threading.Event()
        app._closing = False
        app._process_lock = threading.Lock()
        app._active_process = proc
        app.destroy = destroyed.set

        app._on_close()

        proc.wait(timeout=5)
        self.assertTrue(app._closing)
        self.assertTrue(destroyed.is_set())
        self.assertIsNotNone(proc.poll())


if __name__ == "__main__":
    unittest.main(verbosity=2)

