"""The file a Bambu printer is printing, read for its filament estimate.

The printer measures no filament. The file it prints says how much each
filament of the job weighs and, where it holds G-code, how that weight is
spread over the layers. The file is fetched from the printer's own file
service: FTP over implicit TLS on port 990, with the login the MQTT service
uses. Only a file whose name matches the running job is read, never "the
newest file", and nothing is written to the printer.

What a name may be and what a file's contents mean are shared with the
OrcaSlicer plugin (``_bambu_usage``). The transfer is Edge's own code.
"""

from __future__ import annotations

import ftplib
import hashlib
import posixpath
import socket
import ssl
import time
from typing import Any

from ._bambu_report import _bambu_int
from ._bambu_trust import bambu_certificate_fingerprint
from ._bambu_usage import (
    _MAX_INPUT,
    _bambu_file_candidates,
    _plate_number,
    parse_bambu_consumption_file,
)
from .bambu_tls import CertificateMemory, CertificateRejected, open_printer, resolve_printer

FTPS_PORT = 990
CONTROL_TIMEOUT_S = 5.0
LOOKUP_TIMEOUT_S = 30.0
DIRECTORIES = ("/", "/cache", "/model")
MAX_LISTING = 4096
# What a failed read may raise besides a refused certificate or address.
READ_ERRORS = (OSError, ValueError, EOFError, ftplib.Error)


class _PrinterFtp(ftplib.FTP_TLS):
    """Implicit TLS, with every data connection held to the control connection's peer."""

    def ntransfercmd(
        self, cmd: str, rest: int | str | None = None
    ) -> tuple[socket.socket, int | None]:
        connection, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        control = self.sock
        try:
            if not isinstance(control, ssl.SSLSocket):
                raise CertificateRejected("Bambu file service is not protected")
            secured = self.context.wrap_socket(
                connection, server_hostname=self.host, session=control.session
            )
            # A resumed session continues the control connection that was
            # already checked; a new one has to show the same certificate.
            if not secured.session_reused and secured.getpeercert(True) != control.getpeercert(
                True
            ):
                raise CertificateRejected("Bambu data connection changed certificate")
            return secured, size
        except BaseException:
            connection.close()
            raise


def read_job_estimate(
    host: str,
    *,
    serial: str,
    access_code: str,
    memory: CertificateMemory,
    report: dict[str, Any],
    port: int = FTPS_PORT,
) -> dict[str, Any] | None:
    """The running job's per-filament weights, or None when its file cannot be told apart."""
    candidates = _bambu_file_candidates(report)
    if not candidates:
        return None
    family, sockaddr = resolve_printer(host, port)
    ftp = _PrinterFtp(timeout=CONTROL_TIMEOUT_S)
    ftp.host = str(sockaddr[0])
    deadline = time.monotonic() + LOOKUP_TIMEOUT_S
    try:
        # The file service of these printers does not resume a TLS 1.3 session
        # for its data connections.
        control = open_printer(
            family,
            sockaddr,
            serial=serial,
            pinned=memory.pinned(serial),
            timeout=CONTROL_TIMEOUT_S,
            maximum_version=ssl.TLSVersion.TLSv1_2,
        )
        ftp.sock = control
        ftp.context = control.context
        ftp.af = control.family
        ftp.file = control.makefile("r", encoding=ftp.encoding)
        ftp.welcome = ftp.getresp()
        ftp.login("bblp", access_code)
        memory.remember(serial, bambu_certificate_fingerprint(control.getpeercert(True)))
        ftp.prot_p()
        matches: set[str] = set()
        for directory in DIRECTORIES:
            if time.monotonic() >= deadline:
                raise TimeoutError("Bambu file lookup timed out")
            names: list[str] = []

            def listed(line: str, names: list[str] = names) -> None:
                if len(names) >= MAX_LISTING or time.monotonic() >= deadline:
                    raise ValueError("Bambu file listing exceeds the limit")
                names.append(line)

            try:
                ftp.retrlines("NLST " + directory, listed)
            except ftplib.error_perm:
                continue
            for name in names:
                basename = posixpath.basename(name)
                if basename in candidates and not any(ord(char) < 32 for char in name):
                    matches.add(posixpath.join(directory, basename))
        if len(matches) != 1:
            return None
        path = next(iter(matches))
        ftp.voidcmd("TYPE I")
        size = ftp.size(path)
        if size is None or size <= 0 or size > _MAX_INPUT:
            return None
        data = bytearray()

        def received(chunk: bytes) -> None:
            if len(data) + len(chunk) > _MAX_INPUT or time.monotonic() >= deadline:
                raise ValueError("Bambu print file exceeds the transfer limit")
            data.extend(chunk)

        ftp.retrbinary("RETR " + path, received, blocksize=65536)
        # A file still being written is not the file the job runs from.
        if len(data) != size or ftp.size(path) != size:
            return None
    finally:
        ftp.close()
    named = str(report.get("gcode_file") or "")
    plate_path: str | None = named
    if _plate_number(named) is None:
        index = _bambu_int(report.get("plate_idx"))
        plate_path = f"Metadata/plate_{index}.gcode" if index and index > 0 else None
    estimate: dict[str, Any] | None = parse_bambu_consumption_file(bytes(data), plate_path)
    if estimate is not None:
        estimate["sha256"] = hashlib.sha256(data).hexdigest()
    return estimate
