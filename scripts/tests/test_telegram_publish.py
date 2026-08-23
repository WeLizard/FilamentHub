from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts.telegram_publish import (
    PublicationError,
    parse_draft,
    publish_draft,
    send_telegram_message,
    validate_draft_text,
)


def write_draft(path: Path, *, status: str = "approved", text: str = "Готово.") -> None:
    path.write_text(
        "---\n"
        "project: filamenthub\n"
        "channel: telegram\n"
        "topic: safe-editorial-flow\n"
        f"status: {status}\n"
        "parse_mode: HTML\n"
        "source_from: abc123\n"
        "source_to: def456\n"
        "about_action: none\n"
        "boosty_mode: skip\n"
        "---\n\n"
        f"{text}\n",
        encoding="utf-8",
    )


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TelegramPublisherTest(unittest.TestCase):
    def test_cli_defaults_to_dry_run_without_network_or_ledger_write(self) -> None:
        from scripts.telegram_publish import main

        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            ledger_path = Path(temp) / "ledger.json"
            write_draft(draft_path, text="<b>Проверенный</b> текст.")

            output = io.StringIO()
            with (
                patch("scripts.telegram_publish.urllib.request.urlopen") as request,
                patch("sys.stdout", output),
            ):
                result = main(
                    ["--draft", str(draft_path), "--ledger", str(ledger_path)]
                )

            self.assertEqual(result, 0)
            request.assert_not_called()
            self.assertFalse(ledger_path.exists())
            self.assertIn("Telegram was not contacted", output.getvalue())

    def test_publish_rejects_unapproved_draft_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            write_draft(draft_path, status="draft")
            draft = parse_draft(draft_path)

            with patch("scripts.telegram_publish.urllib.request.urlopen") as request:
                with self.assertRaisesRegex(PublicationError, "status: approved"):
                    publish_draft(
                        draft,
                        token="test-token",
                        channel="@filamenthub_test",
                        ledger_path=Path(temp) / "ledger.json",
                    )
            request.assert_not_called()

    def test_publish_requires_token_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            write_draft(draft_path)
            draft = parse_draft(draft_path)

            with patch("scripts.telegram_publish.urllib.request.urlopen") as request:
                with self.assertRaisesRegex(PublicationError, "BOT_TOKEN"):
                    publish_draft(
                        draft,
                        token="",
                        channel="@filamenthub_test",
                        ledger_path=Path(temp) / "ledger.json",
                    )
            request.assert_not_called()

    def test_successful_publish_records_message_id_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            ledger_path = Path(temp) / "ledger.json"
            write_draft(draft_path, text="<b>Вышло</b> без домыслов.")
            draft = parse_draft(draft_path)

            def opener(*args: object, **kwargs: object) -> FakeResponse:
                return FakeResponse({"ok": True, "result": {"message_id": 321}})

            message_id = publish_draft(
                draft,
                token="test-token",
                channel="@filamenthub_test",
                ledger_path=ledger_path,
                opener=opener,
                now=lambda: datetime(2026, 8, 23, 12, 30, tzinfo=UTC),
            )

            self.assertEqual(message_id, 321)
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(len(ledger["publications"]), 1)
            telegram = ledger["publications"][0]["telegram"]
            self.assertEqual(telegram["status"], "published")
            self.assertEqual(telegram["message_id"], 321)
            self.assertEqual(telegram["published_at"], "2026-08-23T12:30:00Z")

            with self.assertRaisesRegex(PublicationError, "already published"):
                publish_draft(
                    draft,
                    token="test-token",
                    channel="@filamenthub_test",
                    ledger_path=ledger_path,
                    opener=lambda *args, **kwargs: self.fail(
                        "an already published topic must not contact Telegram"
                    ),
                )

    def test_unsupported_html_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            write_draft(draft_path, text="<script>нет</script>")

            with self.assertRaisesRegex(PublicationError, "unsupported HTML tag"):
                validate_draft_text(parse_draft(draft_path))

    def test_transport_error_does_not_expose_bot_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            draft_path = Path(temp) / "post.md"
            write_draft(draft_path)
            draft = parse_draft(draft_path)
            token = "123456:secret-value"

            def opener(*args: object, **kwargs: object) -> FakeResponse:
                raise urllib.error.URLError(f"connection to bot{token} failed")

            with self.assertRaises(PublicationError) as captured:
                send_telegram_message(
                    draft,
                    token=token,
                    channel="@filamenthub_test",
                    opener=opener,
                )

            self.assertNotIn(token, str(captured.exception))
            self.assertIn("<redacted>", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
