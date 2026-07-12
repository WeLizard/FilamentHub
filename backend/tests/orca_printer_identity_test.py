"""Tests for the canonical Orca printer_model resolver.

Printer.name reconstructs the vendor-prefixed Orca machine name (the value Orca
matches compatible_printers_condition against); Printer.model has the vendor
stripped and must not be used. Only system printers carry a canonical name.
"""

from app.models.printer import Printer
from app.services.orca_printer_identity import (
    is_orca_system_printer,
    resolve_orca_printer_model,
)


def test_resolve_uses_name_not_model():
    printer = Printer(name="Bambu Lab X1 Carbon", model="X1 Carbon", source="system")
    assert resolve_orca_printer_model(printer) == "Bambu Lab X1 Carbon"


def test_resolve_none_when_name_empty():
    printer = Printer(name="", model="X1 Carbon", source="system")
    assert resolve_orca_printer_model(printer) is None


def test_system_printer_flag():
    assert is_orca_system_printer(Printer(name="Voron 2.4 350", source="system")) is True
    assert is_orca_system_printer(Printer(name="My Custom Rig", source="user")) is False
