# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub-pr15005-gcode-preview"
# name = "FilamentHub PR15005 G-code Preview Fixture"
# description = "Reproduces the Windows CRLF post-processing case fixed by PR #15005."
# author = "FilamentHub"
# version = "0.0.1"
# ///
"""Minimal runtime fixture for OrcaSlicer PR #15005."""

import os

import orca


class GcodePreviewRewrite(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "PR15005: Rewrite G-code as CRLF"

    def execute(self, ctx):
        step = getattr(ctx, "step", None)
        step_enum = getattr(orca.slicing, "Step", None)
        post_process = getattr(step_enum, "psGCodePostProcess", None)
        if post_process is None:
            post_process = getattr(orca.slicing, "psGCodePostProcess", None)
        if step is not None and post_process is not None and step != post_process:
            return orca.ExecutionResult.skipped("Not the G-code post-process step")

        path = getattr(ctx, "gcode_path", "") or ""
        if not path or not os.path.isfile(path):
            return orca.ExecutionResult.skipped("Host did not provide a G-code file")

        try:
            with open(path, "rb") as handle:
                original = handle.read()

            normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            rewritten = b"; PR15005_CRLF_REWRITE\r\n" + normalized.replace(
                b"\n", b"\r\n"
            )

            with open(path, "wb") as handle:
                handle.write(rewritten)
        except OSError as exc:
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError,
                "G-code rewrite failed: %s" % type(exc).__name__,
            )

        return orca.ExecutionResult.success(
            "Prepended PR15005 marker and rewrote G-code as CRLF"
        )


@orca.plugin
class GcodePreviewFixturePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(GcodePreviewRewrite)
