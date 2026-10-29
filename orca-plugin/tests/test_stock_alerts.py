"""Low-stock alerts reach OrcaSlicer as native notifications, once each."""

import json
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import set_host_attr


def spool_alert(alert_id, name="PLA Red", remaining=42.4):
    return {
        "id": alert_id, "type": "low_stock_spool", "link": "/profile?tab=spools",
        "extra_data": {
            "spool_id": 7, "name": name, "remaining_g": remaining, "threshold_g": 100,
        },
        "created_at": "2026-10-29T10:00:00Z",
    }


def material_alert(alert_id):
    return {
        "id": alert_id, "type": "low_stock_material", "link": None,
        "extra_data": {
            "material_key": "pla", "name": "PLA", "shelf_g": 350,
            "threshold_g": 500, "unknown_count": 2,
        },
        "created_at": "2026-10-29T10:00:00Z",
    }


class Env:
    def __init__(self, plugin, monkeypatch, tmp_path):
        self.plugin = plugin
        self.monkeypatch = monkeypatch
        self.shown = []
        self.requests = []
        self.response = (200, b"", None)
        monkeypatch.setattr(plugin, "STOCK_ALERT_STATE_FILE", str(tmp_path / "alerts.json"))
        monkeypatch.setattr(plugin, "WORKSTATION_KEY_FILE", str(tmp_path / "key.json"))
        monkeypatch.setattr(plugin, "AUTH_FILE", str(tmp_path / "auth.json"))
        monkeypatch.setattr(plugin, "http_get_bearer", self.get)
        monkeypatch.setattr(
            plugin, "open_site_path", lambda path: self.shown.append(("open", path))
        )
        host = plugin.orca.host
        set_host_attr(
            monkeypatch, host, "ui.NotificationLevel",
            SimpleNamespace(WarningNotificationLevel="warning-level"),
        )
        self.accepts_extras = True
        set_host_attr(monkeypatch, host, "ui.push_notification", self.push)
        plugin.save_auth("page-token")

    def push(self, level, text, hyper_text=None, on_click=None):
        self.shown.append((level, text, hyper_text, on_click))

    def get(self, path, token):
        self.requests.append((path, token))
        return self.response

    def serve(self, items, latest):
        body = json.dumps({"items": items, "latest_id": latest}).encode()
        self.response = (200, body, None)

    def texts(self):
        return [item[1] for item in self.shown if item[0] != "open"]


@pytest.fixture
def env(plugin_module, monkeypatch, tmp_path):
    return Env(plugin_module, monkeypatch, tmp_path)


def test_first_poll_without_a_cursor_shows_nothing_and_stores_latest(env):
    env.serve([spool_alert(9)], 9)

    env.plugin.StockAlertRuntime().poll_once()

    assert env.shown == []
    assert env.plugin.load_stock_alert_cursor() == 9
    assert "after_id=0" in env.requests[0][0]


def test_new_alerts_are_shown_once_each_in_id_order(env):
    runtime = env.plugin.StockAlertRuntime()
    env.serve([], 5)
    runtime.poll_once()
    env.serve([material_alert(8), spool_alert(6)], 8)

    runtime.poll_once()
    runtime.poll_once()

    texts = env.texts()
    assert len(texts) == 2
    assert "PLA Red" in texts[0] and "42" in texts[0] and "100" in texts[0]
    assert "350" in texts[1] and "2" in texts[1]
    assert all(item[0] == "warning-level" for item in env.shown)
    assert env.plugin.load_stock_alert_cursor() == 8
    # The click opens the Spools tab through the site-relative helper.
    env.shown[0][3]()
    assert env.shown[-1] == ("open", "/profile?tab=spools")


def test_a_hostile_link_from_the_server_is_not_opened(env):
    runtime = env.plugin.StockAlertRuntime()
    env.serve([], 1)
    runtime.poll_once()
    alert = spool_alert(2)
    alert["link"] = "https://evil.example/x"
    env.serve([alert], 2)

    runtime.poll_once()
    env.shown[0][3]()

    assert env.shown[-1] == ("open", env.plugin.STOCK_ALERT_SPOOLS_PATH)


def test_restart_does_not_repeat_an_alert(env):
    first = env.plugin.StockAlertRuntime()
    env.serve([], 1)
    first.poll_once()
    env.serve([spool_alert(2)], 2)
    first.poll_once()
    assert len(env.texts()) == 1

    restarted = env.plugin.StockAlertRuntime()
    restarted.poll_once()

    assert len(env.texts()) == 1
    assert "after_id=2" in env.requests[-1][0]


def test_a_refused_notification_is_retried_not_lost(env):
    runtime = env.plugin.StockAlertRuntime()
    env.serve([], 1)
    runtime.poll_once()
    env.serve([spool_alert(2)], 2)
    refusing = {"on": True}
    shown = env.push

    def push(level, text, hyper_text=None, on_click=None):
        if refusing["on"]:
            raise RuntimeError("OrcaSlicer is closing")
        shown(level, text, hyper_text, on_click)

    set_host_attr(env.monkeypatch, env.plugin.orca.host, "ui.push_notification", push)

    runtime.poll_once()
    assert env.texts() == [] and env.plugin.load_stock_alert_cursor() == 1
    refusing["on"] = False
    runtime.poll_once()
    assert len(env.texts()) == 1 and env.plugin.load_stock_alert_cursor() == 2


def test_rejected_page_token_does_not_crash_and_is_not_retried(env):
    env.response = (401, b"", None)
    runtime = env.plugin.StockAlertRuntime()

    for _ in range(4):
        runtime.poll_once()

    assert len(env.requests) == 1
    assert env.shown == []
    assert env.plugin.load_saved_auth() is None


def test_rejected_workstation_key_keeps_the_page_token(env, tmp_path):
    (tmp_path / "key.json").write_text(json.dumps({"key": "fhw_abcdefgh12345678"}))
    runtime = env.plugin.StockAlertRuntime()
    env.response = (401, b"", None)

    runtime.poll_once()
    assert env.requests[0][1] == "fhw_abcdefgh12345678"
    assert env.plugin.load_saved_auth()["accessToken"] == "page-token"
    assert (tmp_path / "key.json").exists()

    env.serve([], 3)
    runtime.poll_once()
    assert env.requests[1][1] == "page-token"


def test_key_is_preferred_and_unauthenticated_plugin_is_quiet(env, tmp_path):
    runtime = env.plugin.StockAlertRuntime()
    (tmp_path / "key.json").write_text(json.dumps({"key": "fhw_abcdefgh12345678"}))
    env.serve([], 1)
    runtime.poll_once()
    assert env.requests[0][1] == "fhw_abcdefgh12345678"

    (tmp_path / "key.json").unlink()
    env.plugin.clear_auth()
    runtime.poll_once()
    assert len(env.requests) == 1


def test_throttling_backs_off_and_honours_retry_after(env):
    runtime = env.plugin.StockAlertRuntime()
    env.response = (429, b"", 900.0)

    delay = runtime.poll_once()

    assert delay >= 900.0


def test_hosts_without_extra_arguments_still_show_the_text(env):
    shown = []
    set_host_attr(
        env.monkeypatch, env.plugin.orca.host, "ui.push_notification",
        lambda level, text: shown.append((level, text)),
    )

    assert env.plugin.push_native_notification(
        "WarningNotificationLevel", "Low", hyper_text="Open", on_click=lambda: None
    )

    assert shown == [("warning-level", "Low")]


def test_runtime_thread_polls_and_stops_with_the_plugin(env):
    runtime = env.plugin.StockAlertRuntime()
    env.monkeypatch.setattr(env.plugin, "STOCK_ALERT_FIRST_POLL_RANGE", (0.0, 0.0))
    env.serve([], 4)

    runtime.start()
    thread = runtime._thread
    for _ in range(100):
        if env.requests:
            break
        thread.join(0.05)
    runtime.stop(wait_timeout=2)

    assert env.requests
    assert not thread.is_alive()
