"""Privacy guard: no new hardware/network identity columns (MATERIAL-FOUNDATION-1).

The RFC privacy boundary (material-systems-and-printer-profile-rfc.md §1.2)
forbids storing hardware/network identity of the user's printers. The legacy
columns below predate the boundary and are tracked for a phased cleanup; any
NEW column whose name suggests such identity must go through RFC review first.
"""

from __future__ import annotations

import re

from app.db.base import Base

# Legacy columns that existed before the privacy boundary was drawn.
# Do NOT extend this list without an RFC review.
ALLOWED_IDENTITY_COLUMNS = {
    ("user_printer_devices", "device_fingerprint"),
    ("user_printer_devices", "api_key"),
    ("user_printer_devices", "printer_hostname"),
    ("sync_devices", "device_fingerprint"),
    # User-level Spoolman-compat API key: account credential, not hardware
    # identity, but matched by the pattern below.
    ("users", "api_key"),
}

SUSPICIOUS = re.compile(
    r"(serial|fingerprint|hostname|mac_addr|macaddress|ip_addr|ipaddress|hwid|hardware_id|imei|access_code)",
    re.IGNORECASE,
)


def test_no_new_hardware_identity_columns() -> None:
    violations = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if not SUSPICIOUS.search(column.name):
                continue
            if (table.name, column.name) not in ALLOWED_IDENTITY_COLUMNS:
                violations.append(f"{table.name}.{column.name}")
    assert not violations, (
        "New hardware/network identity column(s) detected: "
        f"{', '.join(sorted(violations))}. The cloud privacy boundary "
        "(material-systems-and-printer-profile-rfc.md §1.2) requires RFC review "
        "before storing such identifiers."
    )


def test_allowlist_entries_still_exist() -> None:
    """The allowlist must not rot: every entry maps to a real column, so a
    cleaned-up legacy column is also removed from the list."""
    stale = []
    for table_name, column_name in ALLOWED_IDENTITY_COLUMNS:
        table = Base.metadata.tables.get(table_name)
        if table is None or column_name not in table.columns:
            stale.append(f"{table_name}.{column_name}")
    assert not stale, f"Stale allowlist entries (column removed?): {', '.join(sorted(stale))}"
