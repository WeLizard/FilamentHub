from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "content" / "editorial" / "publication-log.json"
TELEGRAM_TEXT_LIMIT = 4096
CHANNEL_PATTERN = re.compile(r"(?:@[A-Za-z][A-Za-z0-9_]{4,31}|-100\d{6,})")
TOPIC_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*")
ALLOWED_HTML_TAGS = {
    "a",
    "b",
    "blockquote",
    "code",
    "del",
    "em",
    "i",
    "ins",
    "pre",
    "s",
    "span",
    "strike",
    "strong",
    "tg-emoji",
    "tg-spoiler",
    "u",
}


class PublicationError(ValueError):
    """A safe, user-actionable publication failure."""


@dataclass(frozen=True)
class PublicationDraft:
    path: Path
    project: str
    channel: str
    topic: str
    status: str
    parse_mode: str | None
    source_from: str | None
    source_to: str | None
    about_action: str
    boosty_mode: str
    text: str


class TelegramHTMLValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.text_parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_HTML_TAGS:
            self.errors.append(f"unsupported HTML tag <{tag}>")
            return
        self.open_tags.append(tag)

        attributes = dict(attrs)
        allowed: set[str]
        if tag == "a":
            allowed = {"href"}
            href = attributes.get("href")
            if href is None or not _valid_link(href):
                self.errors.append("<a> requires a safe http(s), tg:// or mailto link")
        elif tag == "span":
            allowed = {"class"}
            if attributes.get("class") != "tg-spoiler":
                self.errors.append('<span> only supports class="tg-spoiler"')
        elif tag == "tg-emoji":
            allowed = {"emoji-id"}
            if not (attributes.get("emoji-id") or "").isdigit():
                self.errors.append("<tg-emoji> requires a numeric emoji-id")
        elif tag == "blockquote":
            allowed = {"expandable"}
            if "expandable" in attributes and attributes["expandable"] not in (
                None,
                "",
                "expandable",
            ):
                self.errors.append("blockquote expandable must be a boolean attribute")
        else:
            allowed = set()

        unexpected = sorted(set(attributes) - allowed)
        if unexpected:
            self.errors.append(
                f"unsupported attribute(s) on <{tag}>: {', '.join(unexpected)}"
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.open_tags and self.open_tags[-1] == tag:
            self.open_tags.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_HTML_TAGS:
            self.errors.append(f"unsupported HTML closing tag </{tag}>")
            return
        if not self.open_tags:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        expected = self.open_tags.pop()
        if expected != tag:
            self.errors.append(f"closing tag </{tag}> does not match <{expected}>")

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.text_parts.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.text_parts.append(html.unescape(f"&#{name};"))


def _valid_link(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if parsed.scheme == "tg":
        return bool(parsed.netloc or parsed.path)
    if parsed.scheme == "mailto":
        return bool(parsed.path)
    return False


def _unquote_frontmatter_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_draft(path: Path) -> PublicationDraft:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublicationError(f"Cannot read draft: {path}") from exc

    lines = raw.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise PublicationError("Draft must start with flat --- frontmatter")

    metadata: dict[str, str] = {}
    body_start: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = index + 1
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or key.strip() in metadata:
            raise PublicationError(f"Invalid frontmatter line {index + 1}")
        metadata[key.strip()] = _unquote_frontmatter_value(value)

    if body_start is None:
        raise PublicationError("Draft frontmatter has no closing --- line")

    required = ("project", "channel", "topic", "status")
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise PublicationError(f"Missing frontmatter: {', '.join(missing)}")

    unknown = sorted(
        set(metadata)
        - {
            *required,
            "about_action",
            "boosty_mode",
            "parse_mode",
            "source_from",
            "source_to",
        }
    )
    if unknown:
        raise PublicationError(f"Unknown frontmatter: {', '.join(unknown)}")

    channel = metadata["channel"].lower()
    if channel != "telegram":
        raise PublicationError("telegram_publish.py accepts only channel: telegram")

    status = metadata["status"].lower()
    if status not in {"draft", "approved"}:
        raise PublicationError("Draft status must be draft or approved")

    topic = metadata["topic"]
    if TOPIC_PATTERN.fullmatch(topic) is None:
        raise PublicationError(
            "topic must use lowercase letters, digits, dots, dashes or underscores"
        )

    raw_parse_mode = metadata.get("parse_mode", "HTML").strip()
    if raw_parse_mode.lower() in {"", "none", "plain"}:
        parse_mode = None
    elif raw_parse_mode.upper() == "HTML":
        parse_mode = "HTML"
    else:
        raise PublicationError("parse_mode must be HTML or none")

    about_action = metadata.get("about_action", "none").lower()
    if about_action not in {"none", "review", "update"}:
        raise PublicationError("about_action must be none, review or update")

    boosty_mode = metadata.get("boosty_mode", "skip").lower()
    if boosty_mode not in {"skip", "crosspost", "expanded"}:
        raise PublicationError("boosty_mode must be skip, crosspost or expanded")

    text = "\n".join(lines[body_start:]).strip()
    if not text:
        raise PublicationError("Draft body is empty")

    draft = PublicationDraft(
        path=path,
        project=metadata["project"],
        channel=channel,
        topic=topic,
        status=status,
        parse_mode=parse_mode,
        source_from=metadata.get("source_from") or None,
        source_to=metadata.get("source_to") or None,
        about_action=about_action,
        boosty_mode=boosty_mode,
        text=text,
    )
    validate_draft_text(draft)
    return draft


def validate_draft_text(draft: PublicationDraft) -> int:
    rendered_text = draft.text
    if draft.parse_mode == "HTML":
        parser = TelegramHTMLValidator()
        try:
            parser.feed(draft.text)
            parser.close()
        except Exception as exc:
            raise PublicationError("Telegram HTML is malformed") from exc
        if parser.open_tags:
            parser.errors.append(
                "unclosed HTML tag(s): "
                + ", ".join(f"<{tag}>" for tag in reversed(parser.open_tags))
            )
        if parser.errors:
            raise PublicationError("; ".join(parser.errors))
        rendered_text = "".join(parser.text_parts)

    length = len(rendered_text.encode("utf-16-le")) // 2
    if length > TELEGRAM_TEXT_LIMIT:
        raise PublicationError(
            f"Telegram text is {length} UTF-16 units; limit is {TELEGRAM_TEXT_LIMIT}"
        )
    return length


def validate_channel(channel: str) -> str:
    channel = channel.strip()
    if CHANNEL_PATTERN.fullmatch(channel) is None:
        raise PublicationError(
            "Telegram channel must be @public_username or a private -100... ID"
        )
    return channel


def dry_run_report(draft: PublicationDraft, channel: str | None) -> str:
    length = validate_draft_text(draft)
    destination = channel.strip() if channel else "<not configured>"
    mode = draft.parse_mode or "plain"
    return (
        "DRY RUN — Telegram was not contacted\n"
        f"Draft: {draft.path}\n"
        f"Destination: {destination}\n"
        f"Status: {draft.status}\n"
        f"Parse mode: {mode}\n"
        f"Length: {length}/{TELEGRAM_TEXT_LIMIT} UTF-16 units\n"
        "---\n"
        f"{draft.text}\n"
        "---"
    )


def _redact(value: str, secret: str) -> str:
    return value.replace(secret, "<redacted>") if secret else value


def send_telegram_message(
    draft: PublicationDraft,
    *,
    token: str,
    channel: str,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> int:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, str] = {
        "chat_id": channel,
        "text": draft.text,
    }
    if draft.parse_mode is not None:
        payload["parse_mode"] = draft.parse_mode
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        response_context = opener(request, timeout=20)
        with response_context as response:  # type: ignore[attr-defined]
            response_data = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except OSError:
            body = ""
        detail = _redact(body, token).strip()
        suffix = f": {detail}" if detail else ""
        raise PublicationError(f"Telegram HTTP error {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        reason = _redact(str(exc.reason), token)
        raise PublicationError(f"Telegram connection failed: {reason}") from exc
    except OSError as exc:
        raise PublicationError("Telegram connection failed") from exc

    try:
        result = json.loads(response_data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PublicationError("Telegram returned invalid JSON") from exc

    if not isinstance(result, dict) or result.get("ok") is not True:
        description = ""
        if isinstance(result, dict):
            description = _redact(str(result.get("description", "")), token)
        suffix = f": {description}" if description else ""
        raise PublicationError(f"Telegram rejected the message{suffix}")

    message = result.get("result")
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not isinstance(message_id, int):
        raise PublicationError("Telegram succeeded without a message_id")
    return message_id


def load_ledger(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "publications": []}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"Cannot read publication ledger: {path}") from exc
    if (
        not isinstance(ledger, dict)
        or ledger.get("version") != 1
        or not isinstance(ledger.get("publications"), list)
    ):
        raise PublicationError(f"Unsupported publication ledger format: {path}")
    return ledger


def write_ledger(path: Path, ledger: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise PublicationError(f"Cannot update publication ledger: {path}") from exc


def ensure_topic_is_unpublished(path: Path, draft: PublicationDraft) -> None:
    ledger = load_ledger(path)
    publications = ledger["publications"]
    assert isinstance(publications, list)
    for item in publications:
        if (
            not isinstance(item, dict)
            or item.get("project") != draft.project
            or item.get("topic") != draft.topic
        ):
            continue
        telegram = item.get("telegram")
        if isinstance(telegram, dict) and telegram.get("status") == "published":
            message_id = telegram.get("message_id", "unknown")
            raise PublicationError(
                f"Topic {draft.topic!r} is already published as message_id={message_id}"
            )


def record_publication(
    path: Path,
    draft: PublicationDraft,
    *,
    message_id: int,
    published_at: datetime,
) -> None:
    ledger = load_ledger(path)
    publications = ledger["publications"]
    assert isinstance(publications, list)

    entry = next(
        (
            item
            for item in publications
            if isinstance(item, dict)
            and item.get("project") == draft.project
            and item.get("topic") == draft.topic
        ),
        None,
    )
    if entry is None:
        entry = {
            "project": draft.project,
            "topic": draft.topic,
            "source": {
                "from": draft.source_from,
                "to": draft.source_to,
            },
            "about": {"action": draft.about_action},
            "telegram": {},
            "boosty": {
                "mode": draft.boosty_mode,
                "status": "not_published",
                "url": None,
            },
        }
        publications.append(entry)

    telegram = entry.setdefault("telegram", {})
    if not isinstance(telegram, dict):
        raise PublicationError("Invalid Telegram entry in publication ledger")
    telegram.update(
        {
            "status": "published",
            "message_id": message_id,
            "published_at": published_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )
    write_ledger(path, ledger)


def publish_draft(
    draft: PublicationDraft,
    *,
    token: str,
    channel: str,
    ledger_path: Path,
    opener: Callable[..., object] = urllib.request.urlopen,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    if draft.status != "approved":
        raise PublicationError("Real publication requires frontmatter status: approved")
    if not token.strip():
        raise PublicationError("TELEGRAM_BOT_TOKEN is not configured")
    channel = validate_channel(channel)
    validate_draft_text(draft)
    ensure_topic_is_unpublished(ledger_path, draft)

    message_id = send_telegram_message(
        draft,
        token=token.strip(),
        channel=channel,
        opener=opener,
    )
    try:
        record_publication(
            ledger_path,
            draft,
            message_id=message_id,
            published_at=now(),
        )
    except PublicationError as exc:
        raise PublicationError(
            "Telegram accepted the message, but the ledger update failed. "
            f"message_id={message_id}; do not publish again. {exc}"
        ) from exc
    return message_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or explicitly publish an approved Telegram draft."
    )
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--channel", help="Override TELEGRAM_CHANNEL_ID")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and render only (default).",
    )
    mode.add_argument(
        "--publish",
        action="store_true",
        help="Send an approved draft through the Telegram Bot API.",
    )
    return parser


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        draft = parse_draft(args.draft)
        configured_channel = args.channel or os.environ.get("TELEGRAM_CHANNEL_ID")
        if not args.publish:
            print(dry_run_report(draft, configured_channel))
            return 0

        message_id = publish_draft(
            draft,
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            channel=configured_channel or "",
            ledger_path=args.ledger,
        )
    except PublicationError as exc:
        print(f"Publication error: {exc}", file=sys.stderr)
        return 2

    print(f"Published to Telegram. message_id={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
