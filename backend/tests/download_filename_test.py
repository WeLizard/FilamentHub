from app.services.download_filename import (
    attachment_content_disposition,
    safe_download_stem,
)


def test_safe_download_stem_keeps_unicode_and_removes_forbidden_characters() -> None:
    assert safe_download_stem("  Тест:<ABS> / 0.4*  ") == "Тест_ABS_ _ 0.4"


def test_safe_download_stem_uses_fallback_for_empty_result() -> None:
    assert safe_download_stem(' :*?" ', "profile") == "profile"


def test_attachment_disposition_has_ascii_and_utf8_names() -> None:
    disposition = attachment_content_disposition("Профиль ABS.json")

    assert 'filename="_______ ABS.json"' in disposition
    assert "filename*=UTF-8''%D0%9F%D1%80%D0%BE%D1%84%D0%B8%D0%BB%D1%8C%20ABS.json" in disposition
