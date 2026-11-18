"""A linked Bambu printer is recognised by its certificate; nobody else gets the access code."""

import hashlib
import shutil
import socket
import ssl
import subprocess
import threading

import pytest

SERIAL = "01S00A123456789"
OTHER_SERIAL = "01S00A987654321"

# SHA-256 of the issuing certificates the plugin carries: the set Bambu Studio
# ships, then the per-model issuers. A change here is a change of who may vouch
# for a printer and has to be deliberate.
BUNDLED_ISSUERS = {
    "e98f19578b3f124ace6b8a247ffeda52dc99c89fd4e7d20c82829977b7f33502",  # BBL CA2 RSA
    "1f99d846718c8d333ac319cb8e70919ab63236090fbadde909ba4a6f0867a683",  # BBL CA2 ECC
    "3d13019b45a4fa8a6cb8dc0fd7becbb19bb2bf0c2fcb9434a9345fa58680da0b",  # BBL CA2 RSA by BBL CA
    "e898483224f9092f575d627433bb21ed9d125a77e3635b0da6fc18fe850a02d7",  # BBL CA2 ECC by BBL CA
    "030bca81cece18b7eff3cfd2b75d09d3efca893bc069609e37fa04257fe4d840",  # BBL CA
    "68bf3182bc32d5a5454f864928abaa291941f6d5ac6a86a0e5ad6ecfe2d5477b",  # BBL Device CA N6-V2
    "6a854d546ed6e3ce7a2112657e53f4555374413e6f5cb55f995d1ddd7c06dc69",  # BBL Device CA N7-V2
    "ce667b6c001d26c34ed97333fb6099699409fc3d4e12429c37baebb05c46c60a",  # BBL Device CA O1C2-V2
}


@pytest.fixture(autouse=True)
def isolated_bambu_storage(plugin_module, monkeypatch, tmp_path):
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(tmp_path / "bambu.json"))


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    """A private CA, printer certificates it issued, and one it did not."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("the openssl command is needed to make test certificates")
    root = tmp_path_factory.mktemp("bambu-pki")
    config = root / "openssl.cnf"
    config.write_text(
        "[req]\ndistinguished_name = dn\nprompt = no\n[dn]\nCN = unused\n"
        "[ca]\nbasicConstraints = critical,CA:TRUE\nkeyUsage = critical,keyCertSign,cRLSign\n",
        encoding="ascii",
    )

    def run(*args):
        subprocess.run(
            [openssl, *args], cwd=root, check=True, capture_output=True, timeout=60
        )

    def key(name):
        run("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
            "-out", name + ".key")

    def self_signed(name, common_name, *extra):
        key(name)
        run("req", "-new", "-x509", "-config", str(config), "-key", name + ".key",
            "-subj", "/CN=" + common_name, "-days", "30", "-out", name + ".pem", *extra)

    def issued(name, common_name):
        key(name)
        run("req", "-new", "-config", str(config), "-key", name + ".key",
            "-subj", "/CN=" + common_name, "-out", name + ".csr")
        run("x509", "-req", "-in", name + ".csr", "-CA", "ca.pem", "-CAkey", "ca.key",
            "-CAcreateserial", "-days", "30", "-out", name + ".pem")

    self_signed("ca", "Test Printer CA", "-extensions", "ca")
    issued("printer", SERIAL)
    issued("reissued", SERIAL)
    issued("neighbour", OTHER_SERIAL)
    self_signed("stranger", SERIAL)
    return root


def _server_context(pki, name):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pki / (name + ".pem"), pki / (name + ".key"))
    return context


class _Printer:
    """Answers TLS on loopback with whichever certificate it is told to present."""

    def __init__(self, pki):
        self._pki = pki
        self._context = None
        self._accepted = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.address = (
            socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
            self._listener.getsockname(),
        )
        threading.Thread(target=self._serve, daemon=True).start()

    def present(self, name):
        self._context = _server_context(self._pki, name)
        pem = (self._pki / (name + ".pem")).read_text(encoding="ascii")
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.strip())).hexdigest()

    def _serve(self):
        while True:
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return
            try:
                self._accepted.append(self._context.wrap_socket(connection, server_side=True))
            except OSError:
                connection.close()

    def close(self):
        self._listener.close()
        for connection in self._accepted:
            connection.close()


@pytest.fixture
def printer(pki):
    server = _Printer(pki)
    yield server
    server.close()


def _link(plugin, serial=SERIAL):
    payload = plugin.configure_bambu_bridge(7, 9, "127.0.0.1", "code1234", serial, "fhpb_token")
    return dict(payload["printers"][0])


def _saved(plugin):
    return plugin.load_bambu_config()["printers"][0]


def _connect(plugin, printer, config):
    """Connect the way the readers do: the certificate is saved once the code is accepted."""
    sock = plugin._open_bambu_tls(printer.address, 5, config)
    try:
        plugin._remember_bambu_certificate(config, sock)
    finally:
        sock.close()


def test_linked_printer_is_recognised_and_a_stranger_is_refused(plugin_module, printer):
    binding = _link(plugin_module)

    # No certificate is saved yet, and this one is not issued by Bambu Lab: a
    # printer the plugin cannot verify still connects, as it did before.
    own = printer.present("printer")
    _connect(plugin_module, printer, binding)
    assert _saved(plugin_module)["certificate"] == own
    _connect(plugin_module, printer, binding)

    # ``binding`` predates the saved certificate, like the copy a long-running
    # reader holds. It must not let another device in.
    printer.present("stranger")
    with pytest.raises(plugin_module.BambuCertificateRejected):
        plugin_module._open_bambu_tls(printer.address, 5, binding)
    assert _saved(plugin_module)["certificate"] == own


def test_certificate_reissued_to_the_same_printer_is_accepted(
    plugin_module, printer, pki, monkeypatch
):
    monkeypatch.setattr(
        plugin_module, "BAMBU_CA_CERTIFICATES", (pki / "ca.pem").read_text(encoding="ascii")
    )
    binding = _link(plugin_module)
    printer.present("printer")
    _connect(plugin_module, printer, binding)

    reissued = printer.present("reissued")
    _connect(plugin_module, printer, binding)
    assert _saved(plugin_module)["certificate"] == reissued

    # Issued by the same authority, but to another printer.
    printer.present("neighbour")
    with pytest.raises(plugin_module.BambuCertificateRejected):
        plugin_module._open_bambu_tls(printer.address, 5, binding)


def test_setup_leaves_the_saved_connection_alone(plugin_module, printer):
    binding = _link(plugin_module)
    printer.present("printer")
    # Setup reads the printer before the binding is written and then requires
    # the saved binding to be unchanged; saving a certificate in between would
    # fail every repeated setup.
    pending = {key: binding[key] for key in (
        "physical_printer_id", "material_system_id", "host", "access_code", "serial",
    )}
    _connect(plugin_module, printer, pending)
    assert _saved(plugin_module) == binding

    _connect(plugin_module, printer, binding)
    assert "certificate" in _saved(plugin_module)
    # The card now points at another printer: the old certificate must not
    # follow it, or the new printer would be refused.
    plugin_module.configure_bambu_bridge(7, 9, "127.0.0.1", "code1234", OTHER_SERIAL, "fhpb_token")
    assert "certificate" not in _saved(plugin_module)


class _FtpsPrinter:
    """Implicit-TLS FTP holding one print file, as much as the plugin's reader uses."""

    FILE = b"print file bytes " * 512

    def __init__(self, pki, data_certificate):
        self._control = _server_context(pki, "printer")
        # ``None`` serves data connections from the control context, so the
        # client can resume its session; a separate context forces a new one.
        self._data = (
            self._control if data_certificate is None
            else _server_context(pki, data_certificate)
        )
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                raw, _ = self._listener.accept()
            except OSError:
                return
            try:
                self._session(self._control.wrap_socket(raw, server_side=True))
            except OSError:
                raw.close()

    def _session(self, control):
        def reply(text):
            control.sendall(text.encode("ascii") + b"\r\n")

        passive = None
        reply("220 ready")
        for line in control.makefile("rb"):
            command, _, argument = line.decode("ascii").strip().partition(" ")
            if command == "USER":
                reply("331 password")
            elif command == "PASS":
                reply("230 in")
            elif command in {"PBSZ", "PROT", "TYPE"}:
                reply("200 ok")
            elif command == "PASV":
                passive = socket.create_server(("127.0.0.1", 0))
                port = passive.getsockname()[1]
                reply("227 Entering Passive Mode (127,0,0,1,%d,%d)" % (port >> 8, port & 255))
            elif command == "SIZE":
                reply("213 %d" % len(self.FILE))
            elif command in {"NLST", "RETR"}:
                body = self.FILE if command == "RETR" else (
                    b"print.gcode.3mf\r\n" if argument == "/cache" else b""
                )
                reply("150 sending")
                raw, _ = passive.accept()
                passive.close()
                try:
                    data = self._data.wrap_socket(raw, server_side=True)
                    data.sendall(body)
                    data.unwrap().close()
                except OSError:
                    raw.close()
                reply("226 done")
            elif command == "QUIT":
                reply("221 bye")
                return
            else:
                reply("502 not here")

    def close(self):
        self._listener.close()


def _read_print_file(plugin, pki, monkeypatch, data_certificate):
    server = _FtpsPrinter(pki, data_certificate)
    monkeypatch.setattr(plugin, "BAMBU_FTPS_PORT", server.port)
    monkeypatch.setattr(
        plugin, "_resolved_bambu_address",
        lambda _host: (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, ("127.0.0.1", 8883)),
    )
    monkeypatch.setattr(plugin, "parse_bambu_consumption_file", lambda data, _plate: {})
    try:
        return plugin.read_bambu_consumption_file(
            _link(plugin), {"gcode_file": "print.gcode.3mf"}
        )
    finally:
        server.close()


@pytest.mark.parametrize("data_certificate", [None, "printer"])
def test_print_file_is_read_from_the_recognised_printer(
    plugin_module, pki, monkeypatch, data_certificate
):
    result = _read_print_file(plugin_module, pki, monkeypatch, data_certificate)

    assert result == {"sha256": hashlib.sha256(_FtpsPrinter.FILE).hexdigest()}
    assert "certificate" in _saved(plugin_module)


def test_print_file_is_not_taken_from_another_device(plugin_module, pki, monkeypatch):
    # The control connection is the printer, but the file would come from
    # somebody else: what it says about filament use must not be believed.
    with pytest.raises(plugin_module.BambuCertificateRejected):
        _read_print_file(plugin_module, pki, monkeypatch, "stranger")


def test_bundled_issuers_are_the_published_bambu_set(plugin_module):
    context = plugin_module._bambu_tls_context(True)
    issuers = {
        hashlib.sha256(der).hexdigest() for der in context.get_ca_certs(binary_form=True)
    }
    assert issuers == BUNDLED_ISSUERS
