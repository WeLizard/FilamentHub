"""Atomic local persistence for credentials, desired state, and retry data."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import StateError

MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_SEQUENCE = 9_223_372_036_854_775_807
MAX_USAGE_OUTBOX_BATCHES = 1024


def _process_user_id() -> int:
    getter = getattr(os, "geteuid", None)
    if getter is None:
        raise StateError("Edge process ownership cannot be verified")
    return int(getter())


@dataclass
class EdgeState:
    instance_id: str = field(default_factory=lambda: f"edge-{uuid.uuid4().hex}")
    bridge_token: str | None = None
    printer_discovery_key: str | None = None
    physical_printer_id: int | None = None
    material_system_id: int | None = None
    pairing_code_digest: str | None = None
    desired_etag: str | None = None
    desired_snapshot: dict[str, Any] | None = None
    last_snapshot_sequence: int = 0
    pending_observation: dict[str, Any] | None = None
    rejected_observation: dict[str, Any] | None = None
    confirmed_device_identity: dict[str, str] | None = None
    last_usage_batch_sequence: int = 0
    usage_outbox: list[dict[str, Any]] = field(default_factory=list)
    usage_tracker: dict[str, Any] | None = None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> EdgeState:
        self._ensure_private_state_directory()
        if self.path.is_symlink():
            raise StateError("Edge state file must not be a symbolic link")
        if not self.path.exists():
            return EdgeState()
        self._validate_existing_state_file()
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
        if state.printer_discovery_key is not None and (
            not isinstance(state.printer_discovery_key, str)
            or len(state.printer_discovery_key) != 64
            or any(c not in "0123456789abcdef" for c in state.printer_discovery_key)
        ):
            raise StateError("Edge discovery key is invalid")
        for binding_id in (state.physical_printer_id, state.material_system_id):
            if binding_id is not None and (
                isinstance(binding_id, bool) or not isinstance(binding_id, int) or binding_id < 1
            ):
                raise StateError("Edge binding identity is invalid")
        if state.confirmed_device_identity is not None:
            identity = state.confirmed_device_identity
            if (
                not isinstance(identity, dict)
                or not isinstance(identity.get("kind"), str)
                or not isinstance(identity.get("token"), str)
                or len(identity["token"]) != 64
                or any(c not in "0123456789abcdef" for c in identity["token"])
            ):
                raise StateError("Confirmed device identity is invalid")
        if state.rejected_observation is not None and not isinstance(
            state.rejected_observation, dict
        ):
            raise StateError("Rejected device evidence is invalid")
        if (state.physical_printer_id is None) != (state.material_system_id is None):
            raise StateError("Edge binding identity is incomplete")
        if state.bridge_token is not None and state.physical_printer_id is None:
            raise StateError("Paired Edge binding identity is missing")
        if state.pairing_code_digest is not None and (
            not isinstance(state.pairing_code_digest, str)
            or len(state.pairing_code_digest) != 64
            or any(character not in "0123456789abcdef" for character in state.pairing_code_digest)
        ):
            raise StateError("Edge pairing digest is invalid")
        if state.desired_snapshot is not None and not isinstance(state.desired_snapshot, dict):
            raise StateError("Cached desired snapshot is invalid")
        if (
            isinstance(state.last_snapshot_sequence, bool)
            or not isinstance(state.last_snapshot_sequence, int)
            or state.last_snapshot_sequence < 0
            or state.last_snapshot_sequence > MAX_SNAPSHOT_SEQUENCE
        ):
            raise StateError("Edge snapshot sequence is invalid")
        if state.pending_observation is not None and not isinstance(
            state.pending_observation,
            dict,
        ):
            raise StateError("Pending observation is invalid")
        if state.pending_observation is not None:
            pending_sequence = state.pending_observation.get("sequence")
            if pending_sequence is not None and (
                isinstance(pending_sequence, bool)
                or not isinstance(pending_sequence, int)
                or pending_sequence < 1
                or pending_sequence != state.last_snapshot_sequence
            ):
                raise StateError("Pending observation sequence is invalid")
            if state.material_system_id is None:
                raise StateError("Pending observation has no Edge binding")
        if (
            isinstance(state.last_usage_batch_sequence, bool)
            or not isinstance(state.last_usage_batch_sequence, int)
            or state.last_usage_batch_sequence < 0
            or state.last_usage_batch_sequence > MAX_SNAPSHOT_SEQUENCE
        ):
            raise StateError("Edge usage batch sequence is invalid")
        if not isinstance(state.usage_outbox, list) or len(state.usage_outbox) > (
            MAX_USAGE_OUTBOX_BATCHES
        ):
            raise StateError("Edge usage outbox is invalid")
        if state.usage_outbox and state.material_system_id is None:
            raise StateError("Edge usage outbox has no binding")
        previous_sequence = 0
        for batch in state.usage_outbox:
            if not isinstance(batch, dict):
                raise StateError("Edge usage outbox batch is invalid")
            sequence = batch.get("sequence")
            events = batch.get("events")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence <= previous_sequence
                or sequence < 1
                or sequence > state.last_usage_batch_sequence
                or not isinstance(events, list)
                or not events
                or len(events) > 128
            ):
                raise StateError("Edge usage outbox batch is invalid")
            previous_sequence = sequence
        if state.usage_tracker is not None and not isinstance(state.usage_tracker, dict):
            raise StateError("Edge usage tracker is invalid")
        return state

    def save(self, state: EdgeState) -> None:
        temporary: Path | None = None
        try:
            self._ensure_private_state_directory()
            if self.path.is_symlink():
                raise StateError("Edge state file must not be a symbolic link")
            payload = json.dumps(
                asdict(state),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if len(payload.encode("utf-8")) > MAX_STATE_BYTES:
                raise StateError("Edge state exceeds the size limit")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            if os.name == "posix":
                self.path.chmod(0o600)
            self._fsync_directory()
            self._validate_existing_state_file()
        except StateError:
            raise
        except OSError as exc:
            raise StateError("Edge state could not be saved") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _ensure_private_state_directory(self) -> None:
        directory = self.path.parent
        if directory.is_symlink():
            raise StateError("Edge state directory must not be a symbolic link")
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise StateError("Edge state directory could not be created") from exc
        if not directory.is_dir():
            raise StateError("Edge state directory is invalid")
        if os.name != "posix":
            return
        metadata = directory.stat()
        if metadata.st_uid != _process_user_id():
            raise StateError("Edge state directory must be owned by the Edge process")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise StateError("Edge state directory permissions must be 0700 or stricter")

    def _validate_existing_state_file(self) -> None:
        try:
            metadata = self.path.lstat()
        except OSError as exc:
            raise StateError("Edge state file could not be inspected") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise StateError("Edge state file must be a regular file")
        if os.name != "posix":
            return
        if metadata.st_uid != _process_user_id():
            raise StateError("Edge state file must be owned by the Edge process")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise StateError("Edge state file permissions must be 0600 or stricter")

    def _fsync_directory(self) -> None:
        if os.name != "posix":
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(self.path.parent, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
