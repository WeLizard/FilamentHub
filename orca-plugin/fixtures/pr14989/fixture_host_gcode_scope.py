# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub-pr14989-host-gcode-scope"
# name = "FilamentHub PR14989 Host G-code Scope Fixture"
# description = "Checks that a host-provided G-code path uses OrcaSlicer's temporary scoped access."
# author = "FilamentHub"
# version = "0.0.1"
# ///
"""PR #14989 host-provided G-code scope conformance fixture."""

import orca


class HostGcodeScopeCapability(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "PR14989: Host G-code scope"

    def execute(self, ctx):
        step = getattr(ctx, "step", None)
        step_enum = getattr(orca.slicing, "Step", None)
        post_process = getattr(step_enum, "psGCodePostProcess", None)
        if post_process is None:
            post_process = getattr(orca.slicing, "psGCodePostProcess", None)
        if step is not None and post_process is not None and step != post_process:
            return orca.ExecutionResult.skipped("Not the G-code post-process step")

        path = getattr(ctx, "gcode_path", "") or ""
        if not path:
            return orca.ExecutionResult.skipped("Host did not provide a G-code path")

        try:
            with open(path, "rb") as handle:
                first_byte = handle.read(1)
        except PermissionError:
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError,
                "Host-provided G-code path was denied",
            )
        except OSError as exc:
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError,
                "Host-provided G-code read failed: %s" % type(exc).__name__,
            )

        marker = first_byte.hex() if first_byte else "empty"
        return orca.ExecutionResult.success(
            "Host-provided G-code read succeeded; first_byte=%s" % marker
        )


@orca.plugin
class HostGcodeScopePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(HostGcodeScopeCapability)
