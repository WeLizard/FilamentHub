"""Durable Edge synchronization loop."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from threading import Event
from typing import Any

from . import __version__
from .cloud import FilamentHubCloud
from .config import EdgeConfig
from .errors import (
    AuthenticationError,
    EdgeError,
    PairingRequired,
    ProviderUnavailable,
    StateError,
)
from .providers.base import EdgeProvider, ProviderSnapshot
from .state import (
    MAX_SNAPSHOT_SEQUENCE,
    MAX_USAGE_OUTBOX_BATCHES,
    EdgeState,
    StateStore,
)
from .usage import (
    LifecycleCheckpointReason,
    capture_pending_usage_event,
    capture_usage_events,
)

logger = logging.getLogger("filamenthub_edge")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pairing_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EdgeRuntime:
    def __init__(
        self,
        *,
        config: EdgeConfig,
        cloud: FilamentHubCloud,
        provider: EdgeProvider,
        store: StateStore,
        state: EdgeState,
    ) -> None:
        self.config = config
        self.cloud = cloud
        self.provider = provider
        self.store = store
        self.state = state

    def run_cycle(self) -> None:
        self._ensure_paired()
        cloud_error: EdgeError | None = None
        try:
            self._flush_pending_observation()
            self._flush_usage_outbox()
            self._pull_desired_snapshot()
        except AuthenticationError:
            raise
        except EdgeError as exc:
            # Cloud outages must not stop local usage collection. Cached desired
            # assignments remain authoritative until synchronization recovers.
            cloud_error = exc
        try:
            snapshot = self.provider.observe()
        except ProviderUnavailable as provider_error:
            self._checkpoint_without_provider(reason="disconnect")
            if cloud_error is None:
                try:
                    self._flush_usage_outbox()
                    self._heartbeat(self.provider.capabilities())
                except AuthenticationError:
                    raise
                except EdgeError as exc:
                    logger.warning("Disconnect checkpoint delivery delayed: %s", exc)
            raise provider_error
        observed_at = _now_iso()
        if len(self.state.usage_outbox) >= MAX_USAGE_OUTBOX_BATCHES:
            raise StateError(
                "Edge usage outbox is full; local counters were left untouched until "
                "synchronization recovers"
            )
        usage_events = capture_usage_events(self.state, snapshot, observed_at=observed_at)
        if usage_events:
            self._enqueue_usage_batch(usage_events)
        else:
            # The cumulative baseline and unflushed sub-checkpoint delta are
            # themselves durable evidence and must survive a restart.
            self.store.save(self.state)
        self._queue_observation(snapshot, observed_at=observed_at)
        if cloud_error is None:
            try:
                self._flush_pending_observation()
                self._flush_usage_outbox()
                self._heartbeat(snapshot.capabilities)
            except AuthenticationError:
                raise
            except EdgeError as exc:
                cloud_error = exc
        if cloud_error is not None:
            raise cloud_error

    def run_forever(self, *, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        backoff = 5
        while not stop.is_set():
            try:
                self.run_cycle()
            except AuthenticationError as exc:
                if self._new_pairing_code_available():
                    logger.warning("Bridge authorization changed; using the new pairing code")
                    self.state.bridge_token = None
                    self.store.save(self.state)
                    backoff = 5
                else:
                    logger.error("%s; create a new Edge pairing code in FilamentHub", exc)
                    backoff = 60
            except PairingRequired as exc:
                logger.error("%s", exc)
                backoff = 60
            except EdgeError as exc:
                logger.warning("Edge synchronization delayed: %s", exc)
                backoff = min(backoff * 2, 300)
            else:
                backoff = 5
                if stop.wait(self.config.sync_interval):
                    break
                continue
            stop.wait(backoff)

    def shutdown(self) -> None:
        """Best-effort durable checkpoint and delivery for SIGTERM/service stop."""
        if self.state.bridge_token is None or self.state.material_system_id is None:
            return
        try:
            self._flush_pending_observation()
            self._flush_usage_outbox()
        except EdgeError as exc:
            logger.warning("Edge shutdown started with pending cloud delivery: %s", exc)
        if len(self.state.usage_outbox) >= MAX_USAGE_OUTBOX_BATCHES:
            logger.error("Edge shutdown checkpoint deferred because the usage outbox is full")
            return

        observed_at = _now_iso()
        try:
            snapshot = self.provider.observe()
        except ProviderUnavailable:
            self._checkpoint_without_provider(reason="shutdown", observed_at=observed_at)
        else:
            events = capture_usage_events(
                self.state,
                snapshot,
                observed_at=observed_at,
                checkpoint_reason="shutdown",
            )
            if events:
                self._enqueue_usage_batch(events)
            else:
                self.store.save(self.state)
            self._queue_observation(snapshot, observed_at=observed_at)

        try:
            self._flush_pending_observation()
            self._flush_usage_outbox()
        except EdgeError as exc:
            logger.warning("Edge shutdown data remains safely queued: %s", exc)

    def reset_connection(self) -> None:
        """Explicitly revoke and clear one idle local binding before a rebind."""
        blockers = self.connection_reset_blockers()
        if blockers:
            raise StateError(
                "Edge connection reset is blocked by durable state: " + ", ".join(blockers)
            )
        if self.state.bridge_token is not None:
            try:
                self.cloud.revoke(token=self.state.bridge_token)
            except AuthenticationError:
                # An owner-side revoke already made the local token harmless.
                pass
        self.state.bridge_token = None
        self.state.physical_printer_id = None
        self.state.material_system_id = None
        self.state.pairing_code_digest = None
        self.state.desired_etag = None
        self.state.desired_snapshot = None
        self.state.last_snapshot_sequence = 0
        self.state.last_usage_batch_sequence = 0
        self.state.usage_tracker = None
        self.store.save(self.state)

    def connection_reset_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.state.pending_observation is not None:
            blockers.append("pending observation")
        if self.state.usage_outbox:
            blockers.append("usage outbox")
        tracker = self.state.usage_tracker
        if isinstance(tracker, dict) and tracker.get("terminal_emitted") is not True:
            blockers.append("active usage tracker")
        return blockers

    def diagnostic_status(self) -> dict[str, Any]:
        return {
            "instance_id": self.state.instance_id,
            "paired": self.state.bridge_token is not None,
            "physical_printer_id": self.state.physical_printer_id,
            "material_system_id": self.state.material_system_id,
            "pending_observation": self.state.pending_observation is not None,
            "usage_outbox_batches": len(self.state.usage_outbox),
            "usage_outbox_events": sum(
                len(batch.get("events", []))
                for batch in self.state.usage_outbox
                if isinstance(batch, dict)
            ),
            "usage_tracker_active": bool(
                isinstance(self.state.usage_tracker, dict)
                and self.state.usage_tracker.get("terminal_emitted") is not True
            ),
            "last_snapshot_sequence": self.state.last_snapshot_sequence,
            "last_usage_batch_sequence": self.state.last_usage_batch_sequence,
            "connection_reset_blockers": self.connection_reset_blockers(),
        }

    def _ensure_paired(self) -> None:
        if self.state.bridge_token is not None:
            if self.state.physical_printer_id is None or self.state.material_system_id is None:
                raise PairingRequired("Stored Edge pairing state is incomplete")
            return
        if not self.config.pairing_code:
            raise PairingRequired("A FilamentHub Edge pairing code is required")
        result = self.cloud.pair(
            pairing_code=self.config.pairing_code,
            provider=self.config.material_provider,
            instance_id=self.state.instance_id,
            version=__version__,
            capabilities=self.provider.capabilities(),
            previous_physical_printer_id=self.state.physical_printer_id,
            previous_material_system_id=self.state.material_system_id,
        )
        self.state.bridge_token = result.bridge_token
        self.state.physical_printer_id = result.physical_printer_id
        self.state.material_system_id = result.material_system_id
        self.state.pairing_code_digest = _pairing_digest(self.config.pairing_code)
        self.store.save(self.state)
        logger.info("Edge paired with physical printer %s", result.physical_printer_id)

    def _new_pairing_code_available(self) -> bool:
        return bool(
            self.config.pairing_code
            and _pairing_digest(self.config.pairing_code) != self.state.pairing_code_digest
        )

    def _context_payload(self) -> dict[str, Any]:
        if self.state.material_system_id is None:
            raise PairingRequired("Edge material system identity is missing")
        return {
            "material_system_id": self.state.material_system_id,
            "provider": self.config.material_provider,
            "transport": "edge_agent",
            "source_instance_id": self.state.instance_id,
        }

    def _flush_pending_observation(self) -> None:
        if self.state.pending_observation is None:
            return
        token = self._token()
        self.cloud.upload_observation(
            token=token,
            payload=self.state.pending_observation,
        )
        self.state.pending_observation = None
        self.store.save(self.state)

    def _flush_usage_outbox(self) -> None:
        while self.state.usage_outbox:
            batch = self.state.usage_outbox[0]
            self.cloud.upload_usage_batch(token=self._token(), payload=batch)
            self.state.usage_outbox.pop(0)
            self.store.save(self.state)

    def _pull_desired_snapshot(self) -> None:
        result = self.cloud.desired_snapshot(
            token=self._token(),
            etag=self.state.desired_etag,
        )
        if not result.changed:
            return
        if result.snapshot is None:
            return
        self.state.desired_etag = result.etag
        self.state.desired_snapshot = result.snapshot
        self.store.save(self.state)
        assigned = sum(
            1
            for slot in result.snapshot.get("slots", [])
            if isinstance(slot, dict) and slot.get("spool") is not None
        )
        logger.info(
            "Desired material state updated: %s slots, %s assigned spools",
            len(result.snapshot.get("slots", [])),
            assigned,
        )

    def _queue_observation(self, snapshot: ProviderSnapshot, *, observed_at: str) -> None:
        if self.state.pending_observation is not None:
            return
        if self.state.last_snapshot_sequence >= MAX_SNAPSHOT_SEQUENCE:
            raise PairingRequired("Edge snapshot sequence is exhausted; reset and pair Edge again")
        self.state.last_snapshot_sequence += 1
        payload = {
            **self._context_payload(),
            "sequence": self.state.last_snapshot_sequence,
            "observed_at": observed_at,
            "printer": snapshot.printer,
            "slots": snapshot.slots,
            "slot_topology_complete": snapshot.slot_topology_complete,
            "inventory_key_digest": snapshot.inventory_key_digest,
        }
        self.state.pending_observation = payload
        self.store.save(self.state)

    def _enqueue_usage_batch(self, events: list[dict[str, Any]]) -> None:
        if len(self.state.usage_outbox) >= MAX_USAGE_OUTBOX_BATCHES:
            raise StateError(
                "Edge usage outbox is full; usage evidence was preserved but synchronization "
                "must recover before another checkpoint can be queued"
            )
        if self.state.last_usage_batch_sequence >= MAX_SNAPSHOT_SEQUENCE:
            raise PairingRequired("Edge usage sequence is exhausted; reset and pair Edge again")
        self.state.last_usage_batch_sequence += 1
        sequence = self.state.last_usage_batch_sequence
        batch_events = []
        for position, event in enumerate(events, start=1):
            batch_events.append(
                {
                    **event,
                    "event_id": f"{self.state.instance_id}:{sequence}:{position}",
                }
            )
        self.state.usage_outbox.append(
            {
                **self._context_payload(),
                "sequence": sequence,
                "events": batch_events,
            }
        )
        self.store.save(self.state)

    def _checkpoint_without_provider(
        self,
        *,
        reason: LifecycleCheckpointReason,
        observed_at: str | None = None,
    ) -> None:
        if len(self.state.usage_outbox) >= MAX_USAGE_OUTBOX_BATCHES:
            raise StateError(
                "Edge usage outbox is full; pending provider evidence was left untouched"
            )
        events = capture_pending_usage_event(
            self.state,
            observed_at=observed_at or _now_iso(),
            reason=reason,
        )
        if events:
            self._enqueue_usage_batch(events)
        else:
            self.store.save(self.state)

    def _heartbeat(self, capabilities: list[str]) -> None:
        self.cloud.heartbeat(
            token=self._token(),
            payload={
                **self._context_payload(),
                "observed_at": _now_iso(),
                "capabilities": capabilities,
            },
        )

    def _token(self) -> str:
        if self.state.bridge_token is None:
            raise PairingRequired("Edge bridge token is missing")
        return self.state.bridge_token
