"""Outgoing email must exist in every interface language, not only Russian."""

import pytest

from app.core.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    _catalog,
    normalize_language,
    resolve_language,
    translate,
    translate_html,
    translate_list,
)
from app.services.email_service import _render


def _flatten(node, prefix=""):
    keys = set()
    for name, value in node.items():
        path = f"{prefix}{name}"
        if isinstance(value, dict):
            keys |= _flatten(value, f"{path}.")
        else:
            keys.add(f"{path}:{type(value).__name__}")
    return keys


def test_every_catalog_carries_the_same_keys_and_shapes():
    reference = _flatten(_catalog(DEFAULT_LANGUAGE))
    for language in SUPPORTED_LANGUAGES:
        assert _flatten(_catalog(language)) == reference, language


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_placeholders_survive_translation(language):
    assert "{brand_name}" not in translate("brandInvite.subject", language, brand_name="Acme")
    assert "Acme" in translate("brandInvite.subject", language, brand_name="Acme")
    assert len(translate_list("brandInvite.benefits", language)) == 5


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_template_renders_in_the_recipient_language(language):
    cases = [
        ("password_reset.html", {"reset_url": "https://filamenthub.ru/r"}),
        ("email_change.html", {"confirm_url": "https://filamenthub.ru/c"}),
        ("brand_status.html", {"brand_name": "Acme", "approved": True, "reason": None}),
        (
            "brand_team_invite.html",
            {"brand_name": "Acme", "invite_url": "u", "site_url": "s", "role_label": "owner"},
        ),
        (
            "brand_invite.html",
            {
                "brand_display": "Acme",
                "invite_url": "u",
                "site_url": "s",
                "contact_email": "hi@filamenthub.ru",
            },
        ),
        ("admin_reply.html", {"body": "text", "body_html": None, "contact_email": "hi@f.ru"}),
        ("admin_reply_plain.html", {"body": "text", "body_html": None, "contact_email": "hi@f.ru"}),
    ]
    for template, context in cases:
        html = _render(template, language=language, subject="Subject", **context)
        assert f'lang="{language}"' in html, template
        assert "{" not in html.split("<body")[1].replace("{{", ""), template


def test_unknown_language_falls_back_instead_of_failing():
    assert resolve_language(None, "", "de") == DEFAULT_LANGUAGE
    assert resolve_language("pt", "ru") == "ru"
    assert normalize_language("ZH-Hans") == "zh"
    assert translate("passwordReset.subject", "de") == translate("passwordReset.subject", "en")


def test_catalog_markup_is_kept_and_values_are_escaped():
    rendered = translate_html("brandInvite.pitch", "en", brand_display="<script>x</script>")
    assert "<span" in rendered
    assert "<script>" not in rendered
