# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub-pr14989-worker-context"
# name = "FilamentHub PR14989 Worker Context Fixture"
# description = "Observes permission handling in a bounded Python worker."
# author = "FilamentHub"
# version = "0.0.1"
# ///
"""PR #14989 worker-context conformance fixture."""

import os
import threading

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


class WorkerContextCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "PR14989: Worker context"

    def execute(self):
        outcome = {}

        def read_marker():
            try:
                with open(SENTINEL, "r", encoding="utf-8") as handle:
                    outcome["value"] = "read allowed; marker_matches=%s" % (
                        handle.read().strip() == EXPECTED_MARKER
                    )
            except PermissionError:
                outcome["value"] = "permission denied"
            except OSError as exc:
                outcome["value"] = "filesystem error (%s)" % type(exc).__name__

        worker = threading.Thread(target=read_marker, daemon=True)
        worker.start()
        worker.join(timeout=15)
        if worker.is_alive():
            return orca.ExecutionResult.success("Outcome: worker timeout")
        return orca.ExecutionResult.success(
            "Outcome: %s" % outcome.get("value", "worker returned no result")
        )


@orca.plugin
class WorkerContextPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(WorkerContextCapability)
