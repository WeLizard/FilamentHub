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


def test_model_match_respects_word_boundaries():
    # The catalog carries a real Creality model named "Hi". Matching by plain
    # substring made it swallow any model containing those letters — a user's
    # "Creality The Machine Spirit" adopted "Hi" through the word "machine".
    from app.api.v1.endpoints.orca_sync import _model_contains

    assert _model_contains("Creality The Machine Spirit", "Hi") is False
    assert _model_contains("The Machine Spirit", "Hi") is False

    # Genuine family matches still work in the narrow direction only.
    assert _model_contains("Ender 3 Pro", "Ender 3") is True
    assert _model_contains("Ender 3", "Ender 3 Pro") is False
    assert _model_contains("Bambu Lab P1S", "P1S") is True
    assert _model_contains("Voron 2.4 350", "Voron 2.4 350") is True

    assert _model_contains("", "Hi") is False
    assert _model_contains("Ender 3", "") is False
