"""What the plugin is allowed to reach for, checked on its source.

OrcaSlicer audits a plugin at run time and OrcaCloud reports on its code before
people install it. Both look at the same things: the modules it loads, programs
and code it could run, and the servers it names. An update must not widen any
of them by accident, so each list below is the whole of what the plugin uses
today. Adding to a list is a decision: say why in the change that does it and
in ``description.md``, where people read what the plugin does on their computer.
"""

from __future__ import annotations

import ast
import re

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT

SOURCES = sorted(PLUGIN_ROOT.glob("filamenthub_*.py"))
OWN_MODULES = {path.stem for path in SOURCES}
ALLOWED_MODULES = OWN_MODULES | {
    "orca",
    # Bundled with OrcaSlicer's Python; only a fallback store of root certificates.
    "certifi",
    "codecs", "concurrent", "contextlib", "csv", "datetime", "gzip", "hashlib", "hmac",
    "html", "inspect", "io", "ipaddress", "json", "math", "os", "posixpath", "queue",
    "random", "re", "secrets", "shutil", "struct", "sys", "tempfile", "threading", "time",
    "uuid", "xml", "zipfile", "zlib",
    # The network: FilamentHub over HTTPS, and printers on the local network.
    "ftplib", "select", "socket", "ssl", "urllib",
    # Opens a FilamentHub page in the person's browser.
    "webbrowser",
}
# Running other code or other programs is never needed for what the plugin does.
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_ATTRIBUTES = {
    ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execve"), ("os", "spawnv"),
    ("os", "spawnl"), ("os", "fork"),
}
ALLOWED_HOSTS = {
    "filamenthub.ru", "filamenthub.club",
    # The development site of a plugin run from source; the build removes it.
    "localhost",
    # XML namespace names inside 3MF files; nothing is requested from them.
    "www.w3.org", "schemas.microsoft.com", "schemas.openxmlformats.org",
}


@pytest.fixture(scope="module", params=SOURCES, ids=lambda path: path.name)
def source(request):
    text = request.param.read_text(encoding="utf-8")
    return ast.parse(text, filename=request.param.name), text


def test_only_known_modules_are_loaded(source):
    tree, _text = source
    loaded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            loaded.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            loaded.add(node.module.split(".")[0])

    assert loaded - ALLOWED_MODULES == set()


def test_no_other_code_or_program_is_run(source):
    tree, _text = source
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id in FORBIDDEN_CALLS:
            found.append((target.id, node.lineno))
        elif (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and (target.value.id, target.attr) in FORBIDDEN_ATTRIBUTES
        ):
            found.append(("%s.%s" % (target.value.id, target.attr), node.lineno))

    assert found == []


def test_no_server_is_named_besides_filamenthub(source):
    _tree, text = source
    hosts = set(re.findall(r"https?://([A-Za-z0-9][A-Za-z0-9.-]*)", text))

    assert hosts - ALLOWED_HOSTS == set()


def test_a_port_is_opened_only_by_the_printer_search(source):
    # OrcaCloud reports a bound socket as a server other programs can reach. The
    # only ones are the listeners of the search a person starts for printers.
    tree, _text = source
    opened = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"bind", "listen"}
            ):
                opened.append(function.name)

    assert set(opened) <= {"discover_lan_printers"}
