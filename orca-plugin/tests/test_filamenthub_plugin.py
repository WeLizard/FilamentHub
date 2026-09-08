"""Setup, discovery and binding contracts."""

from .filamenthub_plugin_test_support import (
    BUILD_PATH,
    json,
    _load_module,
    PLUGIN_PATH,
    PLUGIN_ROOT,
    pytest,
    setup_bind_and_activate,
    setup_manual_probe,
    time,
    tomllib,
)


def test_pep723_and_runtime_versions_match(plugin_module):
    builder = _load_module(BUILD_PATH, "filamenthub_build_under_test")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    metadata = builder.extract_metadata(source)
    assert metadata["tool"]["orcaslicer"]["plugin"]["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["tool"]["orcaslicer"]["plugin"]["network"] == [
        "filamenthub.ru",
        "*.filamenthub.ru",
    ]
    assert metadata["dependencies"] == []
    project = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dynamic"] == ["version"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "filamenthub_plugin.PLUGIN_VERSION"
    }

def test_setup_inventory_does_not_present_detached_binding_as_connected(setup_flow):
    _plugin, catalog, context, results, _uploads = setup_flow
    context["bindings"] = [{"connection_ref": "ref-1", "physical_printer_id": 7, "status": "detached"}]
    catalog._do_printer_setup({"operation": "list", "requestId": "list"}, "token", [
        {"connection_ref": "ref-1", "label": "Workshop", "print_host": "printer.local"},
    ])
    assert results[-1]["candidates"] == []

def test_lan_candidates_are_local_hints_and_cannot_cross_accounts(setup_flow, monkeypatch):
    plugin, catalog, context, results, _uploads = setup_flow
    calls = []
    def search():
        calls.append(True)
        return [{"provider": "bambu", "host": "192.168.1.42", "serial": "SERIAL-42",
                 "label": "Workshop P2S", "source": "network"},
                {"provider": "bambu", "host": "192.168.1.43", "serial": "SERIAL-43",
                 "label": "Workshop P2S", "source": "network"}], False
    monkeypatch.setattr(plugin, "discover_lan_printers", search)
    catalog._do_printer_setup({"operation": "list", "requestId": "legacy-list"}, "token", [
        {"connection_ref": "legacy-moonraker", "print_host": "192.168.1.80:7125"},
    ])
    assert not calls and [item["provider"] for item in results[-1]["candidates"]] == ["moonraker"]
    catalog._do_printer_setup({"operation": "list", "discovery": True, "requestId": "list"}, "token", [])
    listed = results[-1]
    assert listed["ok"] and not listed["discoveryComplete"]
    assert len(listed["candidates"]) == 2
    assert all(item["physicalPrinterId"] is None for item in listed["candidates"])
    assert len({item["connectionRef"] for item in listed["candidates"]}) == 2
    assert "192.168" not in json.dumps(listed) and "SERIAL" not in json.dumps(listed)
    old_ref = listed["candidates"][0]["connectionRef"]
    context.update(account_scope="owner-2", discovery_key="b" * 64)
    catalog._do_printer_setup({"operation": "probe", "requestId": "probe", "connectionRef": old_ref}, "token", [])
    assert results[-1]["code"] == "connection_not_found"
    catalog._do_printer_setup({"operation": "list", "discovery": True, "requestId": "list-2"}, "token", [])
    assert len(calls) == 2 and results[-1]["candidates"][0]["connectionRef"] != old_ref

def test_discovered_moonraker_uses_existing_probe_binding_and_activation(setup_flow, monkeypatch):
    plugin, catalog, context, results, uploads = setup_flow
    monkeypatch.setattr(plugin, "discover_lan_printers", lambda: ([{
        "provider": "moonraker", "host": "192.168.1.50", "label": "Workshop",
        "print_host": "http://192.168.1.50:7125/printer-a", "source": "network",
    }], True))
    catalog._do_printer_setup({"operation": "list", "discovery": True, "requestId": "list"}, "token", [])
    ref = results[-1]["candidates"][0]["connectionRef"]
    native = []
    probe_setup = plugin.probe_printer_setup
    def authenticated_probe(context, connection, origin):
        if connection.get("api_key") != "local-only-key":
            raise ValueError("printer_auth")
        return probe_setup(context, connection, origin)
    monkeypatch.setattr(plugin, "probe_printer_setup", authenticated_probe)
    monkeypatch.setattr(catalog, "_deliver_native_setup", lambda kind, **data: native.append((kind, data)))
    catalog._do_printer_setup({"operation": "probe", "requestId": "probe", "connectionRef": ref,
                              "copy": {"title": "Connect printer"}}, "token", [])
    kind, prompt = native[-1]
    assert kind == "printer-setup-auth-required" and prompt["connectionRef"] == ref
    assert prompt["copy"] == {"title": "Connect printer"}
    assert catalog._printer_discovery["expires"] > time.monotonic() + 590
    assert "192.168" not in json.dumps(results[-1])
    catalog._do_printer_setup({"type": "printer-setup-local", "operation": "probe", "requestId": "probe",
                              "connectionRef": ref, "host": prompt["host"], "apiKey": "local-only-key"}, "token", [])
    probe = results[-1]
    assert probe["ok"] and probe["provider"] == "happy_hare"
    assert "local-only-key" not in json.dumps(probe)
    assert probe["connection"]["origin"] == "local_manual"
    setup_bind_and_activate(catalog, context, probe)
    assert results[-1]["ok"] and uploads
    stored = plugin.local_setup_connections(context)
    assert stored[0]["print_host"] == "http://192.168.1.50:7125/printer-a"
    assert plugin._moonraker_base_url(stored[0]["print_host"]) == stored[0]["print_host"]
    catalog._printer_discovery["expires"] = 0
    context["bindings"] = []
    catalog._do_printer_setup({"operation": "probe", "requestId": "stale", "connectionRef": ref}, "token", [])
    assert results[-1]["code"] == "connection_not_found"

def test_bambu_advertisement_does_not_follow_foreign_locations(plugin_module):
    packet = (b"NOTIFY * HTTP/1.1\r\nNT: urn:bambulab-com:device:3dprinter:1\r\n"
              b"DevName.bambu.com: Workshop P2S\r\nUSN: SERIAL-42\r\nLocation: 192.168.1.42\r\n\r\n")
    result = plugin_module._bambu_announcement(packet, "192.168.1.42")
    assert result["host"] == "192.168.1.42" and result["serial"] == "SERIAL-42"
    assert plugin_module._bambu_announcement(packet, "192.168.1.43") is None
    assert plugin_module._bambu_announcement(packet, "8.8.8.8") is None
    assert plugin_module._bambu_announcement(packet.replace(b"NOTIFY * HTTP/1.1", b"not a response"), "192.168.1.42") is None
    assert plugin_module._bambu_announcement(packet + b"x" * 8192, "192.168.1.42") is None
    for host in ("127.0.0.1", "0.0.0.0", "192.0.2.1", "240.0.0.1", "8.8.8.8"):
        assert not plugin_module._discovery_address(host)

def test_native_bambu_setup_keeps_the_selected_device_and_refresh_request(setup_flow, monkeypatch):
    plugin, catalog, _context, results, _uploads = setup_flow
    calls = []
    def search():
        calls.append(True)
        return [{"provider": "bambu", "host": "192.168.1.42", "serial": "A",
                 "label": "Same model", "source": "network"},
                {"provider": "bambu", "host": "192.168.1.43", "serial": "B",
                 "label": "Same model", "source": "network"}], True
    monkeypatch.setattr(plugin, "discover_lan_printers", search)
    catalog._do_printer_setup({"operation": "list", "discovery": True, "requestId": "list"}, "token", [])
    ref = results[-1]["candidates"][1]["connectionRef"]
    native = []
    monkeypatch.setattr(catalog, "_deliver_native_setup", lambda kind, **data: native.append((kind, data)))
    binding = {"physicalPrinterId": 7, "materialSystemId": 8, "connectionRef": ref,
               "pairingCode": "test-pair", "requestId": "native-search"}
    catalog._do_prepare_bambu(binding, [{"is_current": True, "host_type": "moonraker",
                                       "print_host": "192.168.1.99"}], "token")
    kind, prompt = native[-1]
    assert kind == "bambu-setup-candidates" and prompt["requestId"] == "native-search"
    assert prompt["candidates"][0]["serial"] == "B" and len(prompt["candidates"]) == 2
    assert not prompt["hasSavedConnection"] and len(calls) == 1
    catalog._printer_discovery["scanned"] -= 10
    catalog._do_prepare_bambu(dict(binding, refresh=True), [], "token")
    assert len(calls) == 2

def test_local_setup_requires_device_identity_before_saved_automatic_access(setup_flow, monkeypatch):
    plugin, catalog, context, results, uploads = setup_flow
    monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: None)
    setup_manual_probe(catalog)
    assert results[-1] == {"ok": False, "code": "identity_unavailable"}
    assert not uploads and not plugin.local_setup_connections(context)
    monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "b" * 32)
    setup_manual_probe(catalog)
    setup_bind_and_activate(catalog, context, results[-1])
    assert results[-1]["ok"]
    path, config = plugin._local_setup_config()
    config["connections"][0]["device_identity"] = None
    plugin.write_json_atomic(path, config)
    assert plugin.verified_local_setup_connections("token") == []
    assert len(plugin.local_setup_connections(context)) == 1

def test_mdns_correlates_split_records_and_keeps_txt_credentials_private(plugin_module):
    plugin = plugin_module
    def name(value):
        return b"".join(bytes([len(label)]) + label.encode() for label in value.split(".")) + b"\0"
    def rr(owner, kind, data):
        return name(owner) + plugin.struct.pack("!HHIH", kind, 1, 120, len(data)) + data
    service = "_moonraker._tcp.local"
    instance = "workshop." + service
    answers = [rr(instance, 33, plugin.struct.pack("!HHH", 0, 0, 7125) + name("printer.local")),
               rr("printer.local", 1, b"\xc0\xa8\x01\x32")]
    txt = [b"route_prefix=printer-a", b"https_port=7130", b"u=private-user", b"p=private-password"]
    additions = [rr(service, 12, name(instance)), rr(instance, 16, b"".join(bytes([len(v)]) + v for v in txt))]
    def packet(items):
        return plugin.struct.pack("!6H", 0, 0x8400, 0, len(items), 0, 0) + b"".join(items)
    records = plugin._mdns_records(packet(answers)) + plugin._mdns_records(packet(additions))
    found = plugin._mdns_candidates(records)
    assert found[0]["print_host"] == "https://192.168.1.50:7130/printer-a"
    assert "private-" not in json.dumps(found)
    loop = plugin.struct.pack("!6H", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c"
    assert plugin._mdns_records(loop) == []
    assert plugin._mdns_records(packet(answers)[:-1]) == []
    public = [(n, k, "8.8.8.8" if k == 1 else v) for n, k, v in records]
    assert plugin._mdns_candidates(public) == []

@pytest.mark.parametrize("status,mode,digest,expected", [
    ("bound", "pull", "a" * 64, True),
    ("detached", "pull", "a" * 64, False),
    ("bound", "push", "a" * 64, False),
    ("bound", "pull", "b" * 64, False),
    ("bound", "pull", None, False),
])
def test_setup_inventory_link_requires_this_binding_and_current_inventory(plugin_module, status, mode, digest, expected):
    context = {"bindings": [{"connection_ref": "ref-1", "status": status, "inventory_key_digest": "a" * 64}]}
    snapshot = {"spoolman_support": mode, "inventory_key_digest": digest}
    assert plugin_module.setup_inventory_linked(context, "ref-1", snapshot) is expected
    assert not plugin_module.setup_inventory_linked(context, "other-ref", snapshot)

def test_setup_keeps_secrets_local_and_requires_cloud_binding_before_activation(setup_flow):
    plugin, catalog, context, results, uploads = setup_flow
    setup_manual_probe(catalog)
    probe = results[-1]
    assert probe["ok"] and probe["gateCount"] == 4
    assert "printer.local" not in json.dumps(probe) and "local-secret" not in json.dumps(probe)
    assert len(probe["connection"]["device_identity"]["token"]) == 64
    assert uploads == []
    catalog._do_printer_setup({"operation": "activate", "requestId": "unbound",
                              "physicalPrinterId": 7, "probeId": probe["probeId"]}, "token", [])
    assert not results[-1]["ok"] and uploads == []
    assert plugin._local_setup_config()[1]["connections"] == []
    setup_bind_and_activate(catalog, context, probe)
    assert results[-1]["ok"] and len(uploads) == 1
    stored = plugin.local_setup_connections(context)
    assert len(stored) == 1 and stored[0]["api_key"] == "local-secret"
    setup_bind_and_activate(catalog, context, probe)
    assert results[-1]["ok"] and len(plugin.local_setup_connections(context)) == 1
    setup_manual_probe(catalog)
    assert results[-1]["connection"]["connection_ref"] == probe["connection"]["connection_ref"]

@pytest.mark.parametrize("changed", ["account", "identity", "expired"])
def test_setup_revalidates_preview_before_activating(setup_flow, monkeypatch, changed):
    plugin, catalog, context, results, uploads = setup_flow
    setup_manual_probe(catalog)
    probe = results[-1]
    if changed == "account":
        context["account_scope"] = "another-account"
    elif changed == "identity":
        monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "c" * 32)
    else:
        catalog._printer_setup_pending[probe["probeId"]]["expires"] = 0
    setup_bind_and_activate(catalog, context, probe)
    assert not results[-1]["ok"] and uploads == []
    assert plugin._local_setup_config()[1]["connections"] == []

@pytest.mark.parametrize("status,body", [
    (401, {}), (503, {"result": {"objects": []}}), (200, {"result": []}),
])
def test_setup_does_not_infer_direct_feed_from_a_failed_or_malformed_query(
    setup_flow, monkeypatch, status, body,
):
    plugin, catalog, _context, results, uploads = setup_flow
    monkeypatch.setattr(plugin, "_moonraker_json", lambda *_args, **_kwargs: (status, body, ""))
    setup_manual_probe(catalog)
    assert not results[-1]["ok"] and uploads == []

def test_setup_restored_local_connections_are_account_and_binding_scoped(setup_flow, monkeypatch):
    plugin, catalog, context, results, _uploads = setup_flow
    setup_manual_probe(catalog)
    setup_bind_and_activate(catalog, context, results[-1])
    assert len(plugin.verified_local_setup_connections("token")) == 1
    monkeypatch.setattr(plugin, "_observe_moonraker_identity", lambda _connection: "d" * 32)
    assert plugin.verified_local_setup_connections("token") == []
    assert plugin.local_setup_connections({**context, "account_scope": "other"}) == []
    assert plugin.local_setup_connections({**context, "bindings": []}) == []
    assert plugin.local_setup_connections({**context, "bindings": [
        {**context["bindings"][0], "physical_printer_id": 8},
    ]}) == []

def test_setup_local_form_is_not_impersonated_by_catalog_messages(plugin_module):
    assert "['printer-setup-local', 'prepare-bambu-local', 'configure-bambu-local'].indexOf(data.type) !== -1) return;" in plugin_module.PAGE
    assert "showPrinterSetupOverlay(data)" in plugin_module.PAGE
    assert "st.resultType === 'printer-setup-result'" in plugin_module.PAGE
    assert "key.value = '';" in plugin_module.PAGE

def test_setup_corrupt_local_record_fails_closed(setup_flow):
    plugin, catalog, context, results, _uploads = setup_flow
    setup_manual_probe(catalog)
    setup_bind_and_activate(catalog, context, results[-1])
    path, config = plugin._local_setup_config()
    config["connections"][0]["device_identity"] = "broken"
    plugin.write_json_atomic(path, config, mode=0o600)
    with pytest.raises(ValueError, match="Invalid local printer connection store"):
        plugin.verified_local_setup_connections("token")

def test_bound_profile_and_manual_alias_do_not_make_same_endpoint_ambiguous(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "read_happy_hare_snapshot", lambda _connection: {"gate_count": 4})
    inventory = {"printers": [{"id": 7, "connection_refs": ["profile", "manual"]}]}
    connections = [
        {"connection_ref": "profile", "print_host": "printer.local:7125", "api_key": "key"},
        {"connection_ref": "manual", "print_host": "http://printer.local:7125/", "api_key": "key"},
    ]
    _connection, snapshot, _device, error = plugin_module.resolve_happy_hare_connection(
        "token", connections, 7, inventory,
    )
    assert error is None and snapshot["gate_count"] == 4
    connections[1]["print_host"] = "different-printer.local:7125"
    assert plugin_module.resolve_happy_hare_connection("token", connections, 7, inventory)[3] == "ambiguous_connection"

def test_plugin_hub_version_rejects_prerelease_suffix(plugin_module):
    builder = _load_module(BUILD_PATH, "filamenthub_build_version_test")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    version = plugin_module.PLUGIN_VERSION
    invalid = source.replace(
        f'# version = "{version}"',
        f'# version = "{version}-alpha.1"',
        1,
    )
    with pytest.raises(ValueError, match="numeric X.Y.Z"):
        builder.extract_metadata(invalid)
