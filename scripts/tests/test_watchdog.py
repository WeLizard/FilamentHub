from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import watchdog


SECURE_PROBE = {
    "version": 1,
    "memory_available_mib": 2048,
    "disk_used_percent": 42,
    "reboot_required": False,
    "ssh_policy": {
        "passwordauthentication": "no",
        "permitrootlogin": "no",
        "pubkeyauthentication": "yes",
    },
    "ssh_security_events": [],
}


class WatchdogProbeTest(unittest.TestCase):
    def test_probe_is_parsed_once_and_drives_server_checks(self) -> None:
        with (
            patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
            patch.object(watchdog, "_ask_server", return_value=json.dumps(SECURE_PROBE)) as ask,
        ):
            probe = watchdog.read_server_probe()
            checks = watchdog.collect_checks(probe)

        self.assertEqual(checks["серверный probe"], None)
        self.assertEqual(checks["память"], None)
        self.assertEqual(checks["диск"], None)
        self.assertEqual(checks["SSH-политика"], None)
        ask.assert_called_once_with(watchdog.SERVER_PROBE_COMMAND)

    def test_insecure_effective_ssh_policy_is_reported(self) -> None:
        probe = {
            **SECURE_PROBE,
            "ssh_policy": {
                "passwordauthentication": "yes",
                "permitrootlogin": "yes",
                "pubkeyauthentication": "yes",
            },
        }

        self.assertEqual(
            watchdog.check_ssh_policy(probe),
            "разрешён вход по паролю; разрешён вход root",
        )

    def test_security_event_is_notified_only_once(self) -> None:
        event = {"id": "event-1", "description": "password для root с 203.0.113.7"}
        probe = {**SECURE_PROBE, "ssh_security_events": [event]}
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            with (
                patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
                patch.object(watchdog, "STATE_FILE", state_file),
                patch.object(watchdog, "read_server_probe", return_value=probe),
                patch.object(watchdog, "collect_checks", return_value={}),
                patch.object(watchdog, "notify") as notify,
            ):
                self.assertEqual(watchdog.main(), 0)
                self.assertEqual(watchdog.main(), 0)

            notify.assert_called_once_with(
                "FilamentHub — опасный SSH-вход: password для root с 203.0.113.7"
            )
            if os.name != "nt":
                self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_invalid_probe_fails_closed(self) -> None:
        with (
            patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
            patch.object(watchdog, "_ask_server", return_value="not-json"),
        ):
            self.assertIsNone(watchdog.read_server_probe())
            self.assertEqual(
                watchdog.collect_checks(None)["серверный probe"],
                "не удалось получить безопасный снимок",
            )


if __name__ == "__main__":
    unittest.main()
