"""Up-front permission declaration and the system-browser helper."""

import os
import platform
import socket

import pytest

from .filamenthub_plugin_test_support import _module_with_pages


@pytest.fixture
def logged(plugin_module, monkeypatch):
    lines = []
    monkeypatch.setattr(plugin_module, "fh_log", lines.append)
    return lines


def test_no_request_permissions_on_host_is_skipped(plugin_module, monkeypatch, logged):
    monkeypatch.delattr(plugin_module.orca, "request_permissions", raising=False)

    assert plugin_module.declare_host_permissions() is False
    assert logged == []


def test_modern_host_receives_both_production_origins_and_threading(
    plugin_module, monkeypatch, logged
):
    calls = []
    def modern_host(*, network=(), threading=False):
        calls.append({"network": network, "threading": threading})

    monkeypatch.setattr(plugin_module, "DEV_CONTOUR", False)
    monkeypatch.setattr(plugin_module, "SITE_URL", "https://filamenthub.club")
    monkeypatch.setattr(
        plugin_module.orca, "request_permissions", modern_host, raising=False,
    )

    assert plugin_module.declare_host_permissions() is True
    assert calls == [{
        "network": ["https://filamenthub.ru", "https://filamenthub.club"],
        "threading": True,
    }]
    assert logged == []


@pytest.mark.parametrize("site", ["http://localhost:3000", "https://fh-test.example:4443"])
def test_development_declares_only_its_actual_site(plugin_module, monkeypatch, site):
    calls = []
    monkeypatch.setattr(plugin_module, "DEV_CONTOUR", True)
    monkeypatch.setattr(plugin_module, "SITE_URL", site)
    monkeypatch.setattr(
        plugin_module.orca, "request_permissions",
        lambda **kwargs: calls.append(kwargs), raising=False,
    )

    assert plugin_module.declare_host_permissions() is True
    assert calls == [{"network": [site], "threading": True}]


def test_legacy_host_without_network_keyword_still_receives_threading(
    plugin_module, monkeypatch, logged
):
    calls = []
    def legacy_host(*, threading=False):
        calls.append({"threading": threading})

    monkeypatch.setattr(plugin_module.orca, "request_permissions", legacy_host, raising=False)

    assert plugin_module.declare_host_permissions() is True
    assert calls == [{"threading": True}]
    assert logged == []


def test_fs_read_only_host_is_skipped_quietly(plugin_module, monkeypatch, logged):
    def old_host(fs_read=()):
        raise AssertionError("must not be called with this signature")

    monkeypatch.setattr(plugin_module.orca, "request_permissions", old_host, raising=False)

    assert plugin_module.declare_host_permissions() is False
    assert len(logged) == 1


def test_host_validation_error_is_not_mistaken_for_an_older_signature(
    plugin_module, monkeypatch
):
    calls = []
    def broken(**_kwargs):
        calls.append(_kwargs)
        raise ValueError("called outside plugin discovery context")

    monkeypatch.setattr(plugin_module.orca, "request_permissions", broken, raising=False)

    with pytest.raises(ValueError, match="discovery context"):
        plugin_module.declare_host_permissions()
    assert len(calls) == 1


@pytest.mark.parametrize("message", [
    "permission registry is unavailable",
    "request_permissions() got an unexpected keyword argument 'network'",
])
def test_type_error_from_host_body_is_not_retried(plugin_module, monkeypatch, message):
    calls = []
    def broken(**kwargs):
        calls.append(kwargs)
        raise TypeError(message)

    monkeypatch.setattr(plugin_module.orca, "request_permissions", broken, raising=False)

    with pytest.raises(TypeError) as failure:
        plugin_module.declare_host_permissions()
    assert str(failure.value) == message
    assert len(calls) == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_permission_refusal_aborts_registration_without_retry_or_capabilities(
    plugin_module, monkeypatch, legacy
):
    calls, registered = [], []
    def modern_host(*, network=(), threading=False):
        calls.append((network, threading))
        raise PermissionError("permission denied")

    def legacy_host(*, threading=False):
        calls.append(threading)
        raise PermissionError("permission denied")

    monkeypatch.setattr(
        plugin_module.orca, "request_permissions",
        legacy_host if legacy else modern_host, raising=False,
    )
    monkeypatch.setattr(plugin_module.orca, "register_capability", registered.append)

    with pytest.raises(PermissionError, match="permission denied"):
        plugin_module.FilamentHubPlugin().register_capabilities()
    assert len(calls) == 1
    assert registered == []


def test_explicit_false_from_a_host_shim_is_respected(plugin_module, monkeypatch):
    monkeypatch.setattr(
        plugin_module.orca, "request_permissions", lambda **_kwargs: False, raising=False,
    )
    with pytest.raises(PermissionError, match="permission request denied"):
        plugin_module.declare_host_permissions()


@pytest.mark.parametrize("signature, keyword, unavailable", [
    ("network_http: list[str] = [], threading: bool = False", "network", True),
    ("fs_read: list[str] = []", "threading", True),
    ("network: list[str] = [], threading: bool = False", "network", False),
])
def test_pybind_legacy_signature_detection_does_not_downgrade_supported_arguments(
    plugin_module, signature, keyword, unavailable
):
    # pybind11's binder raises this before entering C++; its TypeError has only
    # the call-site frame, unlike a Python implementation throwing from its body.
    error = TypeError(
        "request_permissions(): incompatible function arguments. "
        "The following argument types are supported:\n"
        "    1. (%s) -> None\n\nInvoked with: kwargs: %s=[]" % (signature, keyword)
    )
    assert plugin_module._unsupported_permission_keyword(len, error, keyword) is unavailable


def test_native_host_error_needs_its_supported_signature_before_fallback(plugin_module):
    # Native bodies do not add a Python traceback frame. Without a pybind
    # signature, this message cannot prove that the binder rejected the call.
    error = TypeError("request_permissions() got an unexpected keyword argument 'network'")
    assert not plugin_module._unsupported_permission_keyword(len, error, "network")


def test_loading_signin_and_diagnostics_never_query_the_computer_hostname(
    monkeypatch, tmp_path
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("opening FilamentHub must not request a cosmetic hostname")

    monkeypatch.setattr(socket, "gethostname", forbidden)
    monkeypatch.setattr(socket, "getfqdn", forbidden)
    monkeypatch.setattr(platform, "node", forbidden)
    monkeypatch.setattr(platform, "platform", forbidden)
    module, registered = _module_with_pages(native_lifecycle=True)
    monkeypatch.setattr(module, "AUTH_FILE", str(tmp_path / "auth.json"))
    monkeypatch.setattr(module, "WORKSTATION_KEY_FILE", str(tmp_path / "key.json"))
    monkeypatch.setattr(module, "SYNC_LOG_FILE", str(tmp_path / "sync.log"))
    monkeypatch.setattr(module, "wake_bambu_bridge_runtime", lambda: None)
    module.FilamentHubPlugin().register_capabilities()
    page = next(cls() for cls in registered if cls is module.FilamentHubPage)
    monkeypatch.setattr(page._catalog, "_auto_sync", lambda **_kwargs: True)

    assert "<!DOCTYPE html>" in page.get_ui()
    for token in ("first-session", "refreshed-session"):
        page.on_message({
            "source": "filamenthub-plugin", "type": "auth-token",
            "bridgeSession": page._catalog._direct_bridge_session,
            "accessToken": token,
        })

    states = [item for item in page.posted_messages if item["type"] == "workstation-key-state"]
    assert len(states) == 2
    assert all(item["name"] == "OrcaSlicer" and item["keyId"] is None for item in states)
    report = module.diagnostic_report_text()
    assert "Python %s\n" % ".".join(map(str, module.sys.version_info[:3])) in report
    assert "OS %s\n" % module.sys.platform in report


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
