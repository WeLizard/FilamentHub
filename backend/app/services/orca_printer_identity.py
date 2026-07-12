"""Canonical OrcaSlicer printer identity for a FilamentHub Printer.

Orca matches ``compatible_printers_condition`` against a machine preset's
``printer_model`` — the vendor-prefixed model name (e.g. "Bambu Lab X1 Carbon").
The bundle importer reconstructs that exact name into ``Printer.name``, while
``Printer.model`` has the vendor prefix stripped ("X1 Carbon") and must NOT be
used for matching. This mirrors ``orcaslicer_machine_exporter``, which already
emits ``Printer.name`` as ``printer_model``.
"""

from app.models.printer import Printer


def resolve_orca_printer_model(printer: Printer) -> str | None:
    """Return the Orca-canonical ``printer_model`` for a printer, or None."""
    name = (printer.name or "").strip()
    return name or None


def is_orca_system_printer(printer: Printer) -> bool:
    """Whether the printer carries an Orca-canonical name.

    Only bundle-imported (system) printers reconstruct a real Orca
    ``printer_model``; user/custom printers have arbitrary names that match no
    machine preset, so callers must not narrow compatibility by their name.
    """
    return printer.source == "system"
