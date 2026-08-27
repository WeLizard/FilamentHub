"""Durable Edge synchronization loop."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .cloud import FilamentHubCloud
from .config import EdgeConfig
from .errors import AuthenticationError, EdgeError, PairingRequired, ProviderUnavailable
from .providers.base import EdgeProvider, ProviderSnapshot
from .state import EdgeState, StateStore

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
        self._flush_pending_observation()
        self._pull_desired_snapshot()
        try:
            snapshot = self.provider.observe()
        except ProviderUnavailable:
            self._heartbeat(self.provider.capabilities())
            raise
        self._queue_and_upload(snapshot)
        self._heartbeat(snapshot.capabilities)

    def run_forever(self) -> None:
        backoff = 5
        while True:
            try:
                self.run_cycle()
            except AuthenticationError as exc:
                if self._new_pairing_code_available():
                    logger.warning("Bridge authorization changed; using the new pairing code")
                    self.state.bridge_token = None
                    self.state.physical_printer_id = None
                    self.state.material_system_id = None
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
                time.sleep(self.config.sync_interval)
                continue
            time.sleep(backoff)

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

    def _queue_and_upload(self, snapshot: ProviderSnapshot) -> None:
        payload = {
            **self._context_payload(),
            "observed_at": _now_iso(),
            "printer": snapshot.printer,
            "slots": snapshot.slots,
            "slot_topology_complete": snapshot.slot_topology_complete,
        }
        self.state.pending_observation = payload
        self.store.save(self.state)
        self.cloud.upload_observation(token=self._token(), payload=payload)
        self.state.pending_observation = None
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
