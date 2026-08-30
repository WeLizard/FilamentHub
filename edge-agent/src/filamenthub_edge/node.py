"""One local node supervising independent adapter connections."""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event
from typing import Any

from .cloud import FilamentHubCloud
from .config import CONNECTION_ID, MAX_CONNECTIONS, EdgeConfig, NodeConfig
from .errors import AuthenticationError, ConfigurationError, EdgeError, PairingRequired, StateError
from .providers.moonraker import MoonrakerProvider
from .runtime import EdgeRuntime
from .state import EdgeState, StateStore
from .storage import JsonStateFile

logger = logging.getLogger("filamenthub_edge.node")
RuntimeFactory = Callable[[EdgeConfig, StateStore, EdgeState], EdgeRuntime]
MAX_KNOWN_CONNECTIONS = 256


def build_connection(config: EdgeConfig, store: StateStore, state: EdgeState) -> EdgeRuntime:
    if config.adapter != "moonraker" or config.material_provider not in {"happy_hare", "legacy"}:
        raise ConfigurationError("This adapter or material provider is not supported")
    return EdgeRuntime(
        config=config,
        store=store,
        state=state,
        cloud=FilamentHubCloud(
            config.filamenthub_url,
            timeout=config.request_timeout,
            allow_insecure_http=config.allow_insecure_cloud,
        ),
        provider=MoonrakerProvider(
            config.moonraker_url,
            api_key=config.moonraker_api_key,
            material_provider=config.material_provider,
            timeout=config.request_timeout,
            filamenthub_url=config.filamenthub_url,
        ),
    )


class EdgeNode:
    def __init__(
        self, config: NodeConfig, *, runtime_factory: RuntimeFactory = build_connection
    ) -> None:
        self.config = config
        self.factory = runtime_factory
        self.manifest = JsonStateFile(config.state_directory / "node.json")
        document = self.manifest.read_document(max_bytes=64 * 1024)
        self.initialized = document is not None
        if document is None:
            document = {
                "node_instance_id": f"edge-{uuid.uuid4().hex}",
                "cloud_origin": config.filamenthub_url,
                "connections": [],
            }
        identity = document.get("node_instance_id")
        known = document.get("connections")
        if (
            not isinstance(identity, str)
            or not identity.startswith("edge-")
            or len(identity) != 37
            or any(c not in "0123456789abcdef" for c in identity[5:])
            or not isinstance(known, list)
            or len(known) > MAX_KNOWN_CONNECTIONS
            or any(not isinstance(key, str) or not CONNECTION_ID.fullmatch(key) for key in known)
            or len(set(known)) != len(known)
        ):
            raise StateError("Edge node identity or connection registry is invalid")
        if document.get("cloud_origin") != config.filamenthub_url:
            raise StateError(
                "This node belongs to a different cloud origin; use a separate state directory"
            )
        self.node_instance_id: str = identity
        self.known_ids: set[str] = set(known)
        self.configured = {item.connection_id: item for item in config.connections}
        self.runtimes: dict[str, EdgeRuntime] = {}
        self.errors: dict[str, str] = {}

    def initialize(self) -> None:
        self.known_ids.update(self.configured)
        if len(self.known_ids) > MAX_KNOWN_CONNECTIONS:
            raise StateError("Edge node connection registry is full")
        self.manifest.write_document(
            {
                "node_instance_id": self.node_instance_id,
                "cloud_origin": self.config.filamenthub_url,
                "connections": sorted(self.known_ids),
            },
            max_bytes=64 * 1024,
        )
        self.initialized = True
        for key, config in self.configured.items():
            if not config.enabled:
                continue
            try:
                self.runtimes[key] = self._build(config)
            except EdgeError as exc:
                self.errors[key] = type(exc).__name__
                logger.error("Connection %s could not start (%s)", key, type(exc).__name__)

    def _build(self, config: EdgeConfig) -> EdgeRuntime:
        store = StateStore(config.state_path)
        state = store.load()
        if state.node_instance_id not in (None, self.node_instance_id):
            raise StateError("Connection state belongs to a different Edge node")
        if state.node_instance_id is None and state.bridge_token is not None:
            raise StateError("Paired connection state has no Edge node identity")
        state.node_instance_id = self.node_instance_id
        store.save(state)
        return self.factory(replace(config, node_instance_id=self.node_instance_id), store, state)

    def _cycle(self, key: str, stop: Event | None = None) -> bool:
        try:
            self.runtimes[key].run_cycle(stop_event=stop)
        except EdgeError as exc:
            self.errors[key] = type(exc).__name__
            logger.warning("Connection %s synchronization delayed (%s)", key, type(exc).__name__)
        except Exception:
            self.errors[key] = "unexpected_error"
            logger.error("Connection %s encountered an unexpected failure", key)
        else:
            self.errors.pop(key, None)
        runtime = self.runtimes[key]
        runtime.state.last_error_code = self.errors.get(key)
        if key not in self.errors and (stop is None or not stop.is_set()):
            runtime.state.last_success_at = datetime.now(timezone.utc).isoformat()
        try:
            runtime.store.save(runtime.state)
        except StateError:
            self.errors[key] = "StateError"
        return key not in self.errors

    def run_once(self) -> bool:
        if not self.runtimes:
            return not self.errors
        with ThreadPoolExecutor(max_workers=len(self.runtimes), thread_name_prefix="edge") as pool:
            results = list(pool.map(self._cycle, self.runtimes))
        return all(results) and not self.errors

    def run_forever(self, stop: Event) -> None:
        if not self.runtimes:
            stop.wait()
            return
        with ThreadPoolExecutor(max_workers=len(self.runtimes), thread_name_prefix="edge") as pool:
            tasks = [pool.submit(self._worker, key, stop) for key in self.runtimes]
            for task in tasks:
                task.result()

    def _worker(self, key: str, stop: Event) -> None:
        runtime = self.runtimes[key]
        delay = 5.0
        try:
            while not stop.is_set():
                success = self._cycle(key, stop)
                if success:
                    delay = 5.0
                    wait = float(runtime.config.sync_interval)
                else:
                    delay = min(delay * 2, 300)
                    wait = (
                        max(delay, 60)
                        if self.errors.get(key)
                        in {
                            AuthenticationError.__name__,
                            PairingRequired.__name__,
                        }
                        else delay
                    )
                stop.wait(wait + random.uniform(0, min(wait * 0.1, 5)))
        finally:
            try:
                runtime.shutdown()
            except Exception:
                logger.error("Connection %s shutdown left queued state for recovery", key)

    def reset_connection(self, key: str) -> None:
        if not self.initialized:
            raise ConfigurationError("Start this Edge node before resetting a connection")
        config = self.configured.get(key)
        if config is None:
            raise ConfigurationError("Restore this connection's configuration before resetting it")
        self._build(config).reset_connection()

    def diagnostic_status(self, *, connection_id: str | None = None) -> dict[str, Any]:
        ids = self.known_ids | self.configured.keys()
        if connection_id is not None:
            if connection_id not in ids:
                raise ConfigurationError("Unknown Edge connection id")
            ids = {connection_id}
        connections = []
        for key in sorted(ids):
            config = self.configured.get(key)
            item: dict[str, Any] = {
                "id": key,
                "name": config.name if config else key,
                "enabled": bool(config and config.enabled),
                "configured": config is not None,
            }
            try:
                path = self.config.state_directory / "connections" / f"{key}.json"
                state = (
                    StateStore(path).load() if path.exists() or path.is_symlink() else EdgeState()
                )
                item.update(
                    {
                        "source_instance_id": state.instance_id if path.exists() else None,
                        "last_success_at": state.last_success_at,
                        "last_error_code": state.last_error_code,
                        "paired": state.bridge_token is not None,
                        "physical_printer_id": state.physical_printer_id,
                        "material_system_id": state.material_system_id,
                        "pending_observation": state.pending_observation is not None,
                        "identity_conflict": state.rejected_observation is not None,
                        "usage_outbox_batches": len(state.usage_outbox),
                        "usage_tracker_active": bool(
                            state.usage_tracker
                            and state.usage_tracker.get("terminal_emitted") is not True
                        ),
                    }
                )
            except EdgeError as exc:
                item["error"] = type(exc).__name__
            if key in self.errors:
                item["error"] = self.errors[key]
            connections.append(item)
        return {
            "node_instance_id": self.node_instance_id if self.initialized else None,
            "initialized": self.initialized,
            "max_connections": MAX_CONNECTIONS,
            "connections": connections,
        }
