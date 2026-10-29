"""The long-lived report-only key: stored when the page hands it over, forgotten on revoke or sign-out."""

import json

import pytest

KEY = "fhw_abcdefgh12345678"


@pytest.fixture
def plugin(plugin_module, monkeypatch, tmp_path):
    monkeypatch.setattr(plugin_module, "WORKSTATION_KEY_FILE", str(tmp_path / "key.json"))
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(tmp_path / "auth.json"))
    monkeypatch.setattr(plugin_module.BAMBU_BRIDGE_RUNTIME, "wake", lambda: None)
    return plugin_module


def make_catalog(plugin):
    catalog = plugin.FilamentHubCatalog()
    catalog._direct_bridge_session = "s"
    catalog._auto_sync = lambda **_kwargs: True
    delivered = []
    catalog._deliver = lambda kind, **data: delivered.append((kind, data))
    return catalog, delivered


def send(catalog, kind, **extra):
    catalog.on_message(
        {"source": "filamenthub-plugin", "bridgeSession": "s", "type": kind, **extra}
    )


def test_page_hands_over_a_key_and_the_plugin_reports_its_id(plugin):
    catalog, delivered = make_catalog(plugin)

    send(catalog, "auth-token", accessToken="t")
    assert delivered[-1][0] == "workstation-key-state"
    assert delivered[-1][1]["keyId"] is None

    send(catalog, "workstation-key", key=KEY, keyId=12)
    send(catalog, "auth-token", accessToken="t2")

    assert plugin.load_workstation_key() == KEY
    assert delivered[-1][1]["keyId"] == 12


@pytest.mark.parametrize(
    "key,key_id",
    [("not-a-key", 3), (KEY, 0), (KEY, "3"), (KEY, True), (None, 3)],
)
def test_malformed_handover_stores_nothing(plugin, key, key_id):
    catalog, _delivered = make_catalog(plugin)

    send(catalog, "workstation-key", key=key, keyId=key_id)

    assert plugin.load_workstation_key() is None


def test_sign_out_forgets_the_key(plugin):
    catalog, _delivered = make_catalog(plugin)
    send(catalog, "workstation-key", key=KEY, keyId=5)

    send(catalog, "auth-logout")

    assert plugin.load_workstation_key() is None


def test_clear_with_expected_key_spares_a_newer_one(plugin):
    plugin.save_workstation_key(KEY, 1)

    plugin.clear_workstation_key("fhw_somethingelse9999")
    assert plugin.load_workstation_key() == KEY

    plugin.clear_workstation_key(KEY)
    assert plugin.load_workstation_key() is None


def test_key_never_reaches_a_diagnostic_report(plugin):
    text = "failed with %s here" % KEY
    for pattern, replacement in plugin._DIAGNOSTIC_SECRET_PATTERNS:
        text = pattern.sub(replacement, text)

    assert KEY not in text


def test_key_file_is_json_with_id(plugin, tmp_path):
    plugin.save_workstation_key(KEY, 9)

    assert json.loads((tmp_path / "key.json").read_text()) == {"key": KEY, "id": 9}
    assert plugin.load_workstation_key_id() == 9
