# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub-pr14989-declared-read"
# name = "FilamentHub PR14989 Declared Read Fixture"
# description = "Validates a declared read permission using synthetic local data."
# author = "FilamentHub"
# version = "0.0.1"
# ///
"""PR #14989 declared-read conformance fixture."""

import os

import orca


LAB_ROOT = os.path.normcase(
    os.path.abspath(r"F:\FilamentHub\references\OrcaSlicer_data")
)
EXPECTED_MARKER = "FILAMENTHUB_ORCA_PERMISSION_FIXTURE_V1"


def _resolve_data_dir():
    path = os.path.abspath(__file__).replace("\\", "/")
    parts = path.split("/")
    for marker in ("orca_plugins", "plugins"):
        if marker in parts:
            return "/".join(parts[: parts.index(marker)])
    return os.path.dirname(os.path.dirname(path))


def _require_isolated_data_dir(path):
    resolved = os.path.normcase(os.path.abspath(path))
    try:
        inside_lab = os.path.commonpath((LAB_ROOT, resolved)) == LAB_ROOT
    except ValueError:
        inside_lab = False
    if not inside_lab:
        raise RuntimeError("Fixture requires the isolated OrcaSlicer data directory")
    return resolved


DATA_DIR = _require_isolated_data_dir(_resolve_data_dir())
SENTINEL = os.path.join(DATA_DIR, "sentinels", "declared-read.txt")


class DeclaredReadCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "PR14989: Declared read"

    def execute(self):
        try:
            with open(SENTINEL, "r", encoding="utf-8") as handle:
                marker_matches = handle.read().strip() == EXPECTED_MARKER
        except PermissionError:
            return orca.ExecutionResult.success("Outcome: permission denied")
        except OSError as exc:
            return orca.ExecutionResult.success(
                "Outcome: filesystem error (%s)" % type(exc).__name__
            )

        return orca.ExecutionResult.success(
            "Outcome: read allowed; marker_matches=%s" % marker_matches
        )


@orca.plugin
class DeclaredReadPlugin(orca.base):
    def register_capabilities(self):
        orca.request_permissions(fs_read=[SENTINEL])
        orca.register_capability(DeclaredReadCapability)
