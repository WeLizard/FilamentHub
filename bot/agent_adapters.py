from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from typing import Iterable


TG_PROMPT_SUFFIX = (
    "\n\n[Output goes to Telegram. Be concise: only the final result, "
    "no tool details, no file dumps. Max 3-5 sentences or a short list.]"
)


@dataclass(frozen=True)
class PreparedRun:
    command: list[str]
    session_ref: str | None
    persistent: bool


class BaseAgentAdapter:
    name: str
    timeout: int
    command_path: str
    supports_persistent_sessions: bool

    def __init__(self, name: str, command_path: str, timeout: int) -> None:
        self.name = name
        self.command_path = command_path
        self.timeout = timeout
        self.supports_persistent_sessions = False

    def is_available(self) -> bool:
        return os.path.isfile(self.command_path) or bool(self.command_path)

    def prepare_run(self, prompt: str, session_ref: str | None, output_path: str | None) -> PreparedRun:
        raise NotImplementedError

    def resolve_session_ref(self, raw_lines: Iterable[str], prepared_session_ref: str | None) -> str | None:
        return prepared_session_ref


class ClaudeAdapter(BaseAgentAdapter):
    def __init__(self, command_path: str, timeout: int) -> None:
        super().__init__("claude", command_path, timeout)
        self.supports_persistent_sessions = True

    def prepare_run(self, prompt: str, session_ref: str | None, output_path: str | None) -> PreparedRun:
        del output_path
        final_prompt = prompt + TG_PROMPT_SUFFIX
        if session_ref:
            command = [
                self.command_path,
                "-p",
                final_prompt,
                "--output-format",
                "text",
                "--resume",
                session_ref,
            ]
            return PreparedRun(command=command, session_ref=session_ref, persistent=True)

        new_session_ref = str(uuid.uuid4())
        command = [
            self.command_path,
            "-p",
            final_prompt,
            "--output-format",
            "text",
            "--session-id",
            new_session_ref,
        ]
        return PreparedRun(command=command, session_ref=new_session_ref, persistent=True)


class CodexAdapter(BaseAgentAdapter):
    SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{8,})")

    def __init__(self, command_path: str, timeout: int) -> None:
        super().__init__("codex", command_path, timeout)
        self.supports_persistent_sessions = True

    def prepare_run(self, prompt: str, session_ref: str | None, output_path: str | None) -> PreparedRun:
        final_prompt = prompt + TG_PROMPT_SUFFIX
        command = [self.command_path, "exec"]
        if session_ref:
            command.extend(["resume", session_ref])
        if output_path:
            command.extend(["--output-last-message", output_path])
        command.append(final_prompt)
        return PreparedRun(command=command, session_ref=session_ref, persistent=True)

    def resolve_session_ref(self, raw_lines: Iterable[str], prepared_session_ref: str | None) -> str | None:
        if prepared_session_ref:
            return prepared_session_ref
        for line in raw_lines:
            match = self.SESSION_RE.search(line)
            if match:
                return match.group(1)
        return None


class StatelessPrintAdapter(BaseAgentAdapter):
    def __init__(self, name: str, command_path: str, timeout: int) -> None:
        super().__init__(name, command_path, timeout)

    def prepare_run(self, prompt: str, session_ref: str | None, output_path: str | None) -> PreparedRun:
        del session_ref, output_path
        final_prompt = prompt + TG_PROMPT_SUFFIX
        command = [self.command_path, "-p", final_prompt, "--approval-mode", "yolo"]
        return PreparedRun(command=command, session_ref=None, persistent=False)


def build_agent_adapters(config: dict[str, dict[str, object]]) -> dict[str, BaseAgentAdapter]:
    return {
        "claude": ClaudeAdapter(str(config["claude"]["cmd"]), int(config["claude"]["timeout"])),
        "codex": CodexAdapter(str(config["codex"]["cmd"]), int(config["codex"]["timeout"])),
        "qwen": StatelessPrintAdapter("qwen", str(config["qwen"]["cmd"]), int(config["qwen"]["timeout"])),
        "gemini": StatelessPrintAdapter("gemini", str(config["gemini"]["cmd"]), int(config["gemini"]["timeout"])),
    }
