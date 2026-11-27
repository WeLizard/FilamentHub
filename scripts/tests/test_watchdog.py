from __future__ import annotations

import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.parse
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

HEALTHY_EMBED_CSP = (
    "default-src 'self'; "
    "frame-ancestors 'self';"
)


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b'<html><body><div id="root"></div></body></html>',
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]


class WatchdogEmbedTest(unittest.TestCase):
    def response(self, **headers: str) -> FakeResponse:
        return FakeResponse(
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Security-Policy": HEALTHY_EMBED_CSP,
                **headers,
            }
        )

    def test_healthy_embed_contract_passes(self) -> None:
        with patch.object(watchdog.urllib.request, "urlopen", return_value=self.response()):
            self.assertIsNone(watchdog.check_embed())

    def test_missing_csp_is_reported(self) -> None:
        response = FakeResponse(headers={"Content-Type": "text/html"})
        with patch.object(watchdog.urllib.request, "urlopen", return_value=response):
            self.assertIn("не содержит Content-Security-Policy", watchdog.check_embed() or "")

    def test_missing_root_marker_is_reported(self) -> None:
        response = self.response()
        response.body = b"<html><body>empty shell</body></html>"
        with patch.object(watchdog.urllib.request, "urlopen", return_value=response):
            self.assertIn("корневой маркер", watchdog.check_embed() or "")

    def test_x_frame_options_is_rejected(self) -> None:
        with patch.object(
            watchdog.urllib.request,
            "urlopen",
            return_value=self.response(**{"X-Frame-Options": "SAMEORIGIN"}),
        ):
            self.assertIn("запрещённый X-Frame-Options", watchdog.check_embed() or "")

    def test_broad_frame_ancestor_is_rejected(self) -> None:
        response = self.response(
            **{
                "Content-Security-Policy": (
                    "default-src 'self'; frame-ancestors 'self' https://example.com;"
                )
            }
        )
        with patch.object(watchdog.urllib.request, "urlopen", return_value=response):
            self.assertIn("недопустимый frame-ancestors", watchdog.check_embed() or "")


class WatchdogProbeTest(unittest.TestCase):
    def test_probe_is_parsed_once_and_drives_server_checks(self) -> None:
        with (
            patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
            patch.object(watchdog, "BASE_CHECKS", {}),
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

    def test_reboot_required_does_not_claim_a_kernel_update(self) -> None:
        with (
            patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
            patch.object(watchdog, "BASE_CHECKS", {}),
        ):
            checks = watchdog.collect_checks({**SECURE_PROBE, "reboot_required": True})

        self.assertEqual(
            checks["перезагрузка ОС"],
            "операционная система сообщает, что после обновления требуется перезагрузка",
        )

    def test_unchanged_reboot_required_is_not_repeated_the_next_day(self) -> None:
        problem = "операционная система сообщает, что после обновления требуется перезагрузка"
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text(
                json.dumps({"перезагрузка ОС": problem, "_day": "2000-01-01"}),
                encoding="utf-8",
            )
            with (
                patch.object(watchdog, "SERVER", "filamenthub-watchdog@server"),
                patch.object(watchdog, "STATE_FILE", state_file),
                patch.object(watchdog, "read_server_probe", return_value=SECURE_PROBE),
                patch.object(
                    watchdog,
                    "collect_checks",
                    return_value={"перезагрузка ОС": problem},
                ),
                patch.object(watchdog, "notify") as notify,
            ):
                self.assertEqual(watchdog.main(), 1)

            notify.assert_not_called()

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


class WatchdogNotifySecurityTest(unittest.TestCase):
    def test_notify_blocks_curl_config_directive_injection(self) -> None:
        hostile_text = (
            'FilamentHub — API: bad "quote"\n'
            'url = "http://127.0.0.1:9/exfil"\n'
            'output = "pwned.txt"\r\n'
            "@/etc/passwd \\ backslash"
        )
        with (
            patch.dict(
                os.environ,
                {
                    "BOT_TOKEN": '123456:ABC-DEF"\ninjected = "1"',
                    "CHAT_ID": '-10042"\noutput = "bad"',
                    "TELEGRAM_PROXY_URL": 'socks5h://127.0.0.1:1080"\nurl = "http://evil"',
                },
                clear=False,
            ),
            patch.object(watchdog.subprocess, "run") as run_mock,
        ):
            run_mock.return_value.returncode = 0
            run_mock.return_value.stderr = ""
            watchdog.notify(hostile_text)

        run_mock.assert_called_once()
        stdin_cfg: str = run_mock.call_args.kwargs["input"]
        lines = stdin_cfg.splitlines()
        directives = [line.split("=", 1)[0].strip() for line in lines]
        self.assertEqual(
            directives,
            ["url", "data", "max-time", "silent", "show-error", "proxy"],
        )
        data_line = next(line for line in lines if line.startswith("data = "))
        raw_form = data_line.split('"', 1)[1].rsplit('"', 1)[0]
        decoded = urllib.parse.parse_qs(raw_form)
        self.assertEqual(decoded["text"][0], hostile_text)
        self.assertEqual(decoded["chat_id"][0], '-10042"\noutput = "bad"')

    @unittest.skipUnless(shutil.which("curl"), "needs curl binary")
    def test_notify_roundtrip_with_real_curl_against_loopback(self) -> None:
        captured: dict[str, str] = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                captured["path"] = self.path
                captured["body"] = self.rfile.read(length).decode("utf-8")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *_args: object) -> None:
                return None

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_port
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()

        hostile = 'alert "with quotes"\noutput = "should_not_exist.txt"\r\n@/etc/hosts'
        real_quote = watchdog._curl_config_quote

        def rewrite_to_loopback(val: str) -> str:
            val = val.replace("https://api.telegram.org", f"http://127.0.0.1:{port}")
            return real_quote(val)

        try:
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k not in {"TELEGRAM_PROXY_URL", "TELEGRAM_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}
            }
            clean_env["BOT_TOKEN"] = "999:TEST_TOK"
            clean_env["CHAT_ID"] = "-100777"
            with (
                patch.dict(os.environ, clean_env, clear=True),
                patch.object(watchdog, "_curl_config_quote", side_effect=rewrite_to_loopback),
            ):
                watchdog.notify(hostile)
            worker.join(timeout=3)
        finally:
            server.server_close()

        self.assertEqual(captured.get("path"), "/bot999:TEST_TOK/sendMessage")
        parsed = urllib.parse.parse_qs(captured.get("body", ""))
        self.assertEqual(parsed.get("chat_id"), ["-100777"])
        self.assertEqual(parsed.get("text"), [hostile])


if __name__ == "__main__":
    unittest.main()
