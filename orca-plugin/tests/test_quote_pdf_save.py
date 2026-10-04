"""Saving a quotation PDF handed over by the embedded page."""

import base64

import pytest

from .filamenthub_plugin_test_support import json, _module_with_pages

PDF = b"%PDF-1.4\n%test\n"


def _encoded(payload=PDF):
    return base64.b64encode(payload).decode("ascii")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Quote 12.pdf", "Quote 12.pdf"),
        ("Quote 12", "Quote 12.pdf"),
        ("Коммерческое предложение.PDF", "Коммерческое предложение.pdf"),
        ("../../etc/passwd", "passwd.pdf"),
        (r"C:\Users\me\a.pdf", "a.pdf"),
        ('a<b>c:d"e|f?g*h.pdf', "a_b_c_d_e_f_g_h.pdf"),
        ("tab\tname\x00.pdf", "tab_name_.pdf"),
        ("CON", "_CON.pdf"),
        ("nul.pdf", "_nul.pdf"),
        ("com1.txt.pdf", "_com1.txt.pdf"),
        ("", "quote.pdf"),
        ("  ..  ", "quote.pdf"),
        (None, "quote.pdf"),
        ("a" * 400, "a" * 120 + ".pdf"),
    ],
)
def test_pdf_file_name_is_made_safe(raw, expected):
    module, _ = _module_with_pages()
    assert module.sanitize_pdf_file_name(raw) == expected


def test_quote_pdf_is_saved_without_overwriting(tmp_path, monkeypatch):
    module, _ = _module_with_pages()
    monkeypatch.setattr(module, "downloads_folder", lambda: str(tmp_path / "Downloads"))

    ok, first, error = module.save_quote_pdf("КП.pdf", _encoded())
    ok2, second, _ = module.save_quote_pdf("КП.pdf", _encoded(PDF + b"2"))
    ok3, third, _ = module.save_quote_pdf("КП", _encoded())

    assert (ok, error, ok2, ok3) == (True, "", True, True)
    assert [p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in (first, second, third)] == [
        "КП.pdf", "КП (2).pdf", "КП (3).pdf",
    ]
    assert open(first, "rb").read() == PDF
    assert open(second, "rb").read() == PDF + b"2"
    assert sorted(p.name for p in (tmp_path / "Downloads").iterdir()) == [
        "КП (2).pdf", "КП (3).pdf", "КП.pdf",
    ]


@pytest.mark.parametrize(
    "encoded, error",
    [
        (_encoded(b"<html>not a pdf</html>"), "invalid-data"),
        ("not base64 !!!", "invalid-data"),
        ("%PDF-", "invalid-data"),
        ("", "invalid-data"),
        (None, "invalid-data"),
        ("TOO_LARGE", "too-large"),
    ],
)
def test_invalid_quote_pdf_is_refused_and_nothing_is_written(tmp_path, monkeypatch, encoded, error):
    module, _ = _module_with_pages()
    monkeypatch.setattr(module, "downloads_folder", lambda: str(tmp_path / "Downloads"))

    if encoded == "TOO_LARGE":
        encoded = _encoded(b"%PDF-" + b"0" * (20 * 1024 * 1024))
    ok, path, code = module.save_quote_pdf("q.pdf", encoded)

    assert (ok, path, code) == (False, None, error)
    assert not (tmp_path / "Downloads").exists()


def test_write_failure_is_reported(tmp_path, monkeypatch):
    module, _ = _module_with_pages()
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(module, "downloads_folder", lambda: str(blocker / "Downloads"))

    assert module.save_quote_pdf("q.pdf", _encoded()) == (False, None, "write-failed")


def test_page_message_saves_opens_and_answers(tmp_path, monkeypatch):
    module, _ = _module_with_pages()
    page = module.FilamentHubPage()
    page.get_ui()
    monkeypatch.setattr(module, "downloads_folder", lambda: str(tmp_path / "Downloads"))
    opened = []
    monkeypatch.setattr(module, "open_in_system_browser", lambda path: opened.append(path) or True)
    monkeypatch.setattr(module.BACKGROUND_WORKER, "submit", lambda job, *a: job(*a), raising=False)

    assert "quote-pdf-save-v1" in module.PLUGIN_CAPABILITIES

    def send(**extra):
        page.on_message(json.dumps({
            "source": "filamenthub-plugin",
            "type": "save-quote-pdf",
            "bridgeSession": page._catalog._direct_bridge_session,
            **extra,
        }))

    send(requestId="r1", fileName="Offer.pdf", data=_encoded())
    send(requestId="r2", fileName="Offer.pdf", data=_encoded(b"nope"))

    saved, refused = page.posted_messages[-2:]
    assert saved == {
        "source": "filamenthub-host", "type": "quote-pdf-saved", "requestId": "r1",
        "ok": True, "fileName": "Offer.pdf", "folder": "Downloads", "error": "",
    }
    assert refused["ok"] is False and refused["error"] == "invalid-data"
    assert refused["requestId"] == "r2" and refused["fileName"] == ""
    assert len(opened) == 1 and opened[0].endswith("Offer.pdf")
