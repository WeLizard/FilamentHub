"""Why a Bambu LAN setup failed: the step, the message and the report to the site."""

from .filamenthub_plugin_test_support import (
    _bambu_mqtt_packet,
    _bambu_report,
    _bambu_snapshot_socket,
    _BambuMqttSocket,
    json,
    Path,
    pytest,
)


@pytest.fixture(autouse=True)
def isolated_bambu_storage(plugin_module, monkeypatch, tmp_path):
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(tmp_path / "bambu.json"))
    monkeypatch.setattr(plugin_module, "BAMBU_REVOKE_FILE", str(tmp_path / "revoke.json"))
    monkeypatch.setattr(plugin_module, "AUTH_FILE", str(tmp_path / "auth.json"))


def _read(plugin_module, monkeypatch, sock, serial="SERIAL-2"):
    monkeypatch.setattr(plugin_module, "_open_bambu_mqtt", lambda *_args: sock)
    return plugin_module.read_bambu_lan_snapshot(
        {"host": "printer.local", "access_code": "local-secret", "serial": serial},
        timeout=1,
    )


def test_refused_access_code_is_marked_as_the_auth_step(plugin_module, monkeypatch):
    with pytest.raises(PermissionError) as raised:
        _read(plugin_module, monkeypatch, _bambu_snapshot_socket(plugin_module, connack_code=5))

    assert getattr(raised.value, "fh_bambu_stage", None) == "auth"


def test_refused_subscription_is_marked_as_its_own_step(plugin_module, monkeypatch):
    # SUBACK return code 0x80: the broker took the login but refused the topic.
    sock = _BambuMqttSocket([
        _bambu_mqtt_packet(plugin_module, 0x20, bytes([0, 0])),
        _bambu_mqtt_packet(plugin_module, 0x90, b"\x00\x01\x80"),
    ])
    with pytest.raises(ConnectionError) as raised:
        _read(plugin_module, monkeypatch, sock)

    assert getattr(raised.value, "fh_bambu_stage", None) == "subscribe"


def test_silence_after_a_good_login_is_marked_as_the_report_step(plugin_module, monkeypatch):
    with pytest.raises(TimeoutError) as raised:
        _read(plugin_module, monkeypatch, _bambu_snapshot_socket(plugin_module))

    assert getattr(raised.value, "fh_bambu_stage", None) == "report"


def test_public_address_is_marked_before_any_connection(plugin_module):
    with pytest.raises(ValueError) as raised:
        plugin_module._resolved_bambu_address("8.8.8.8")

    assert getattr(raised.value, "fh_bambu_stage", None) == "address"


def _tagged(error, stage):
    error.fh_bambu_stage = stage
    return error


@pytest.mark.parametrize(
    ("error", "serial_given", "expected"),
    [
        (_tagged(ValueError("public"), "address"), False, ("address", "bambuNotLocal")),
        (_tagged(OSError("no such host"), "address"), False, ("address", "bambuUnreachable")),
        (_tagged(ConnectionRefusedError(), "connect"), False, ("connect", "bambuUnreachable")),
        (_tagged(TimeoutError(), "connect"), False, ("connect", "bambuUnreachable")),
        (_tagged(OSError("handshake"), "tls"), False, ("tls", "bambuTlsFailed")),
        (_tagged(ValueError("bad packet"), "auth"), False, ("auth", "bambuTlsFailed")),
        (_tagged(PermissionError(), "auth"), False, ("auth", "bambuLanAuthRejected")),
        (_tagged(ConnectionError(), "subscribe"), False, ("subscribe", "bambuSubscriptionRejected")),
        (_tagged(TimeoutError(), "report"), True, ("report", "bambuNoReport")),
        (_tagged(TimeoutError(), "report"), False, ("report", "bambuNoReportSerial")),
        (OSError("untagged"), False, ("unknown", "bambuInvalid")),
    ],
)
def test_each_step_gets_its_own_message(plugin_module, error, serial_given, expected):
    assert plugin_module.bambu_setup_failure(error, serial_given) == expected


def test_certificate_mismatch_keeps_its_message_whatever_the_step(plugin_module):
    error = _tagged(plugin_module.BambuCertificateRejected("other printer"), "report")

    assert plugin_module.bambu_setup_failure(error, True) == ("tls", "bambuCertificateRejected")


def test_every_failure_message_is_translated_in_english(plugin_module):
    english = json.loads(
        (Path(plugin_module.__file__).parent / "filamenthub_locales" / "en.json").read_text(encoding="utf-8")
    )
    for key in ("bambuNotLocal", "bambuUnreachable", "bambuTlsFailed", "bambuSubscriptionRejected",
                "bambuNoReport", "bambuNoReportSerial", "bambuPairingExpired", "bambuSiteUnreachable"):
        assert english[key]


def _configure(plugin_module, monkeypatch, *, read=None, pair_status=500, serial=""):
    monkeypatch.setattr(plugin_module, "_resolved_bambu_address", lambda _host: None)
    monkeypatch.setattr(
        plugin_module, "read_bambu_lan_snapshot",
        read or (lambda _config: ("SERIAL-42", _bambu_report())),
    )
    monkeypatch.setattr(
        plugin_module, "load_bambu_config",
        lambda: {"source_instance_id": "fixture-instance-0001", "printers": []},
    )
    monkeypatch.setattr(plugin_module, "save_bambu_config", lambda _payload: None)
    monkeypatch.setattr(plugin_module, "http_post_json", lambda *_args: (pair_status, b"{}"))
    results = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_native_setup", lambda _kind, **data: results.append(data))
    catalog._do_configure_bambu(3, 5, "printer.local", "secret", serial, "pair-code-1", "setup-1")
    return results


def _raise(error):
    def read(_config):
        raise error
    return read


def test_failed_check_shows_the_step_message_and_reports_it(
    plugin_module, monkeypatch, setup_attempt_reports
):
    error = _tagged(TimeoutError("quiet"), "report")
    results = _configure(plugin_module, monkeypatch, read=_raise(error))

    assert results == [{"requestId": "setup-1", "ok": False, "code": "bambuNoReportSerial"}]
    assert setup_attempt_reports == [
        ("pair-code-1", "bambu", "orca_plugin_lan", "report", "bambuNoReportSerial"),
    ]


def test_refused_access_code_still_says_so(plugin_module, monkeypatch, setup_attempt_reports):
    results = _configure(
        plugin_module, monkeypatch, read=_raise(_tagged(PermissionError(), "auth")), serial="SERIAL-42",
    )

    assert results[0]["code"] == "bambuLanAuthRejected"
    assert setup_attempt_reports[0][3:] == ("auth", "bambuLanAuthRejected")


def test_expired_site_code_is_named_after_a_good_printer_check(
    plugin_module, monkeypatch, setup_attempt_reports
):
    results = _configure(plugin_module, monkeypatch, pair_status=401)

    assert results[0]["code"] == "bambuPairingExpired"
    assert setup_attempt_reports[0][3:] == ("pair", "bambuPairingExpired")


def test_unreachable_site_is_named_and_not_reported_to_it(
    plugin_module, monkeypatch, setup_attempt_reports
):
    results = _configure(plugin_module, monkeypatch, pair_status=0)

    assert results[0]["code"] == "bambuSiteUnreachable"
    assert setup_attempt_reports == []


def test_success_sends_no_failure_report(plugin_module, monkeypatch, setup_attempt_reports):
    def pair(path, _token, _payload):
        assert path == "/printer-bridge/pair"
        return 200, json.dumps({
            "bridge_token": "fhpb_fresh", "physical_printer_id": 3,
            "material_system_id": 5, "printer_discovery_key": "a" * 64,
        }).encode("utf-8")

    monkeypatch.setattr(plugin_module, "http_post_bridge_json", lambda *_args: (200, b"{}", None))
    monkeypatch.setattr(plugin_module, "wake_bambu_bridge_runtime", lambda: None)
    monkeypatch.setattr(plugin_module, "configure_bambu_bridge", lambda *args, **kwargs: {
        "source_instance_id": "fixture-instance-0001",
        "printers": [{"physical_printer_id": 3, "material_system_id": 5, "host": "printer.local",
                      "serial": "SERIAL-42", "bridge_token": "fhpb_fresh"}],
    })
    monkeypatch.setattr(plugin_module, "build_bambu_bridge_snapshot", lambda *_args: {})
    monkeypatch.setattr(plugin_module, "_resolved_bambu_address", lambda _host: None)
    monkeypatch.setattr(plugin_module, "read_bambu_lan_snapshot", lambda _config: ("SERIAL-42", _bambu_report()))
    monkeypatch.setattr(plugin_module, "load_bambu_config",
                        lambda: {"source_instance_id": "fixture-instance-0001", "printers": []})
    monkeypatch.setattr(plugin_module, "save_bambu_config", lambda _payload: None)
    monkeypatch.setattr(plugin_module, "http_post_json", pair)
    results = []
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver_native_setup", lambda _kind, **data: results.append(data))

    catalog._do_configure_bambu(3, 5, "printer.local", "secret", "", "pair-code-1", "setup-1")

    assert results == [{"requestId": "setup-1", "ok": True, "code": "bambuSaved"}]
    assert setup_attempt_reports == []


def test_report_carries_the_step_and_nothing_about_the_printer(plugin_module, monkeypatch):
    sent = []
    monkeypatch.setattr(plugin_module, "http_post_json", lambda path, token, payload: (
        sent.append((path, token, payload)) or (204, b"")
    ))
    monkeypatch.setattr(plugin_module, "plugin_source_instance_id", lambda: "fixture-instance-0001")

    status = plugin_module.real_report_setup_attempt(
        "pair-code-1", "bambu", "orca_plugin_lan", "report", "bambuNoReport",
    )

    assert status == 204
    path, token, payload = sent[0]
    assert (path, token) == ("/printer-bridge/setup-attempt", "")
    assert set(payload) == {"pairing_code", "provider", "transport", "source_instance_id",
                            "stage", "code", "plugin_version", "platform"}
    assert payload["stage"] == "report" and payload["code"] == "bambuNoReport"
    assert payload["platform"] in {"windows", "macos", "linux", "other"}


def test_report_needs_a_real_pairing_code(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "http_post_json", lambda *_args: pytest.fail("must not send"))

    assert plugin_module.real_report_setup_attempt("", "bambu", "orca_plugin_lan", "dialog", "cancelled") is None


def test_closing_the_bambu_window_reports_a_cancel_in_the_background(plugin_module, monkeypatch):
    submitted = []
    monkeypatch.setattr(plugin_module.BACKGROUND_WORKER, "submit",
                        lambda function, *args: submitted.append((function, args)) or True)
    catalog = plugin_module.FilamentHubCatalog()
    monkeypatch.setattr(catalog, "_deliver", lambda *_args, **_kwargs: True)
    catalog._local_dialog_context = {"provider": "bambu", "physicalPrinterId": 3,
                                     "materialSystemId": 5, "pairingCode": "pair-code-1"}

    catalog._report_local_dialog_state(False, "cancelled")
    catalog._report_local_dialog_state(False, "saved")

    assert [args for _function, args in submitted] == [
        ("pair-code-1", "bambu", "orca_plugin_lan", "dialog", "cancelled"),
    ]
    assert submitted[0][0] is plugin_module.report_printer_bridge_setup_attempt


def test_first_setup_window_searches_instead_of_saying_nothing_was_saved(plugin_module):
    page = plugin_module.LOCAL_DIALOG_PAGE

    assert "bambuLocalConfigMissing" not in page
    assert "!data.hasSavedConnection&&!autoSearched){autoSearched=true;prepare(true)}" in page
    assert "document.getElementById('serial-wrap').open=true" in page
