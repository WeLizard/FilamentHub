"""Atomic local persistence for credentials, desired state, and retry data."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import StateError

MAX_STATE_BYTES = 4 * 1024 * 1024


@dataclass
class EdgeState:
    instance_id: str = field(default_factory=lambda: f"edge-{uuid.uuid4().hex}")
    bridge_token: str | None = None
    physical_printer_id: int | None = None
    material_system_id: int | None = None
    pairing_code_digest: str | None = None
    desired_etag: str | None = None
    desired_snapshot: dict[str, Any] | None = None
    pending_observation: dict[str, Any] | None = None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> EdgeState:
        if not self.path.exists():
            return EdgeState()
        try:
            if self.path.stat().st_size > MAX_STATE_BYTES:
                raise StateError("Edge state file exceeds the size limit")
            decoded = json.loads(self.path.read_text(encoding="utf-8"))
        except StateError:
            raise
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise StateError("Edge state file is invalid") from exc
        if not isinstance(decoded, dict):
            raise StateError("Edge state must be a JSON object")
        state = EdgeState()
        for name in asdict(state):
            if name in decoded:
                setattr(state, name, decoded[name])
        if not isinstance(state.instance_id, str) or len(state.instance_id) < 16:
            raise StateError("Edge instance identity is invalid")
        if state.bridge_token is not None and (
            not isinstance(state.bridge_token, str) or not state.bridge_token.startswith("fhpb_")
        ):
            raise StateError("Edge bridge token is invalid")
        if state.desired_snapshot is not None and not isinstance(state.desired_snapshot, dict):
            raise StateError("Cached desired snapshot is invalid")
        if state.pending_observation is not None and not isinstance(
            state.pending_observation,
            dict,
        ):
            raise StateError("Pending observation is invalid")
        return state

    def save(self, state: EdgeState) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            payload = json.dumps(
                asdict(state),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            temporary.write_text(payload, encoding="utf-8")
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise StateError("Edge state could not be saved") from exc
