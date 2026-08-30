"""Atomic local persistence for credentials, desired state, and retry data."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .errors import StateError
from .storage import JsonStateFile

MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_SEQUENCE = 9_223_372_036_854_775_807
MAX_USAGE_OUTBOX_BATCHES = 1024


@dataclass
class EdgeState:
    instance_id: str = field(default_factory=lambda: f"edge-{uuid.uuid4().hex}")
    node_instance_id: str | None = None
    last_success_at: str | None = None
    last_error_code: str | None = None
    bridge_token: str | None = field(default=None, repr=False)
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


class StateStore(JsonStateFile):
    def load(self) -> EdgeState:
        decoded = self.read_document(max_bytes=MAX_STATE_BYTES)
        if decoded is None:
            return EdgeState()
        state = EdgeState()
        for name in asdict(state):
            if name in decoded:
                setattr(state, name, decoded[name])
        for value in (state.node_instance_id, state.last_success_at, state.last_error_code):
            if value is not None and (not isinstance(value, str) or len(value) > 100):
                raise StateError("Edge node diagnostics are invalid")
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
        self.write_document(asdict(state), max_bytes=MAX_STATE_BYTES)
