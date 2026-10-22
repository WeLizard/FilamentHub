"""Up-front permission declaration and the system-browser helper."""

import os

import pytest


@pytest.fixture
def logged(plugin_module, monkeypatch):
    lines = []
    monkeypatch.setattr(plugin_module, "fh_log", lines.append)
    return lines


def test_no_request_permissions_on_host_is_skipped(plugin_module, monkeypatch, logged):
    monkeypatch.delattr(plugin_module.orca, "request_permissions", raising=False)

    assert plugin_module.declare_host_permissions() is False
    assert logged == []


def test_host_accepting_kwargs_receives_only_threading(plugin_module, monkeypatch, logged):
    calls = []
    monkeypatch.setattr(
        plugin_module.orca, "request_permissions",
        lambda **kwargs: calls.append(kwargs), raising=False,
    )

    assert plugin_module.declare_host_permissions() is True
    assert calls == [{"threading": True}]


def test_fs_read_only_host_is_skipped_quietly(plugin_module, monkeypatch, logged):
    def old_host(fs_read=()):
        raise AssertionError("must not be called with this signature")

    monkeypatch.setattr(plugin_module.orca, "request_permissions", old_host, raising=False)

    assert plugin_module.declare_host_permissions() is False
    assert len(logged) == 1


def test_host_error_never_breaks_plugin_load(plugin_module, monkeypatch, logged):
    def broken(**_kwargs):
        raise ValueError("called outside plugin discovery context")

    monkeypatch.setattr(plugin_module.orca, "request_permissions", broken, raising=False)

    assert plugin_module.declare_host_permissions() is False
    assert "ValueError" in logged[0]


def test_open_in_system_browser_falls_back_to_webbrowser(plugin_module, monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(plugin_module.sys, "platform", "linux")

    assert plugin_module.open_in_system_browser("https://filamenthub.ru/x") is True
    assert opened == ["https://filamenthub.ru/x"]


def test_open_in_system_browser_uses_startfile_on_windows(plugin_module, monkeypatch):
    started = []
    monkeypatch.setattr(plugin_module.sys, "platform", "win32")
    monkeypatch.setattr(plugin_module.os, "startfile", started.append, raising=False)

    assert plugin_module.open_in_system_browser("https://filamenthub.ru/x") is True
    assert started == ["https://filamenthub.ru/x"]


def test_heavy_modules_are_not_loaded_by_the_plugin_import():
    source = open(
        os.path.join(os.path.dirname(__file__), "..", "filamenthub_plugin.py"),
        encoding="utf-8",
    ).read()
    for line in source.splitlines():
        assert line not in {"import ftplib", "import webbrowser", "import ctypes"}
    assert "ctypes" not in source
