from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from test_runtime import FakeCloud, FakeProvider

from filamenthub_edge.cloud import DesiredResult, PairingResult
from filamenthub_edge.config import MAX_CONNECTIONS, MAX_OPTIONS_BYTES, EdgeConfig, NodeConfig
from filamenthub_edge.errors import (
    ConfigurationError,
    HttpRequestError,
    ProviderUnavailable,
    StateError,
)
from filamenthub_edge.node import EdgeNode
from filamenthub_edge.providers.base import ProviderSnapshot
from filamenthub_edge.runtime import EdgeRuntime
from filamenthub_edge.state import StateStore
from filamenthub_edge.storage import NodeLease


class EdgeNodeTest(unittest.TestCase):
    def config(self, directory: Path, count: int = 2) -> NodeConfig:
        return NodeConfig(
            "https://filamenthub.test",
            directory,
            tuple(
                EdgeConfig(
                    filamenthub_url="https://filamenthub.test",
                    pairing_code="FH-AAAAA-BBBBB",
                    material_provider="happy_hare" if index % 2 else "legacy",
                    moonraker_url=f"http://printer-{index}.test",
                    moonraker_api_key=None,
                    state_path=directory / "connections" / f"printer-{index}.json",
                    sync_interval=30,
                    request_timeout=2,
                    allow_insecure_cloud=False,
                    run_once=True,
                    connection_id=f"printer-{index}",
                    name=f"Printer {index}",
                )
                for index in range(count)
            ),
        )

    @staticmethod
    def factory(config, store, state):
        cloud = FakeCloud()
        cloud.fail_upload = False
        return EdgeRuntime(
            config=config, store=store, state=state, provider=FakeProvider(), cloud=cloud
        )

    def test_two_and_ten_connections_share_node_not_source_or_queues(self) -> None:
        for count in (2, 10):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                config = self.config(Path(directory), count)
                with NodeLease(config.state_directory):
                    node = EdgeNode(config, runtime_factory=self.factory)
                    node.initialize()
                    self.assertTrue(node.run_once())
                self.assertEqual(len({r.state.instance_id for r in node.runtimes.values()}), count)
                self.assertEqual(
                    {r.config.node_instance_id for r in node.runtimes.values()},
                    {node.node_instance_id},
                )
                for runtime in node.runtimes.values():
                    self.assertEqual(runtime.state.last_snapshot_sequence, 1)
                    self.assertEqual(len(runtime.cloud.uploads), 1)
                restarted = EdgeNode(config, runtime_factory=self.factory)
                restarted.initialize()
                self.assertEqual(restarted.node_instance_id, node.node_instance_id)
                self.assertEqual(
                    [r.state.instance_id for r in restarted.runtimes.values()],
                    [r.state.instance_id for r in node.runtimes.values()],
                )

    def test_blocked_provider_does_not_block_another_connection(self) -> None:
        second_finished = threading.Event()

        class WaitingProvider(FakeProvider):
            def observe(self):
                if not second_finished.wait(3):
                    raise AssertionError("Other connection was blocked")
                raise ProviderUnavailable("First printer is offline")

        class HealthyProvider(FakeProvider):
            def observe(self):
                second_finished.set()
                return super().observe()

        def factory(config, store, state):
            runtime = self.factory(config, store, state)
            runtime.provider = (
                WaitingProvider() if config.connection_id == "printer-0" else HealthyProvider()
            )
            return runtime

        with tempfile.TemporaryDirectory() as directory:
            node = EdgeNode(self.config(Path(directory)), runtime_factory=factory)
            node.initialize()
            self.assertFalse(node.run_once())
            self.assertTrue(second_finished.is_set())
            self.assertEqual(node.errors, {"printer-0": "ProviderUnavailable"})
            self.assertEqual(len(node.runtimes["printer-1"].cloud.uploads), 1)

    def test_disabled_or_removed_connection_keeps_its_own_retry_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory))
            node = EdgeNode(config, runtime_factory=self.factory)
            node.initialize()
            runtime = node.runtimes["printer-0"]
            runtime.cloud.fail_upload = True
            self.assertFalse(node.run_once())
            self.assertIsNotNone(runtime.state.pending_observation)
            next_config = replace(config, connections=(config.connections[1],))
            restarted = EdgeNode(next_config, runtime_factory=self.factory)
            restarted.initialize()
            self.assertTrue(restarted.run_once())
            report = restarted.diagnostic_status()["connections"]
            removed = next(item for item in report if item["id"] == "printer-0")
            self.assertFalse(removed["configured"])
            self.assertTrue(removed["pending_observation"])
            self.assertIsNotNone(
                StateStore(config.connections[0].state_path).load().pending_observation
            )

    def test_cloud_origin_change_cannot_send_saved_tokens_to_another_server(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory))
            node = EdgeNode(config, runtime_factory=self.factory)
            node.initialize()
            with self.assertRaisesRegex(StateError, "different cloud"):
                EdgeNode(replace(config, filamenthub_url="https://another.test"))

    def test_node_lease_rejects_a_second_writer_and_releases_after_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with NodeLease(path):
                with self.assertRaisesRegex(StateError, "Another Edge process"):
                    with NodeLease(path):
                        self.fail("A second writer acquired the node")
            with NodeLease(path):
                pass

    def test_status_of_an_unstarted_node_does_not_create_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-created"
            node = EdgeNode(self.config(path), runtime_factory=self.factory)
            report = node.diagnostic_status()
            self.assertFalse(report["initialized"])
            self.assertIsNone(report["node_instance_id"])
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ConfigurationError, "Start this Edge"):
                node.reset_connection("printer-0")
            self.assertFalse(path.exists())

    def test_bad_state_and_unsupported_adapter_are_isolated_at_startup(self) -> None:
        for failure in ("state", "adapter"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                config = self.config(Path(directory))
                if failure == "state":
                    path = config.connections[0].state_path
                    path.parent.mkdir(mode=0o700)
                    path.write_text("broken private state", encoding="utf-8")
                    path.chmod(0o600)
                else:
                    config = replace(
                        config,
                        connections=(
                            replace(config.connections[0], adapter="unsupported"),
                            config.connections[1],
                        ),
                    )

                def factory(connection, store, state):
                    if connection.adapter == "unsupported":
                        raise ConfigurationError("secret must not appear in diagnostics")
                    return self.factory(connection, store, state)

                node = EdgeNode(config, runtime_factory=factory)
                node.initialize()
                self.assertFalse(node.run_once())
                self.assertEqual(len(node.runtimes["printer-1"].cloud.uploads), 1)
                report = json.dumps(node.diagnostic_status())
                self.assertNotIn("secret must", report)
                self.assertNotIn("fhpb_fixture", report)

    def test_disabled_connection_resumes_with_the_same_identity_and_pending_observation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory))
            original = EdgeNode(config, runtime_factory=self.factory)
            original.initialize()
            runtime = original.runtimes["printer-0"]
            runtime.cloud.fail_upload = True
            self.assertFalse(original.run_once())
            pending = runtime.state.pending_observation
            disabled = EdgeNode(
                replace(
                    config,
                    connections=(
                        replace(config.connections[0], enabled=False),
                        config.connections[1],
                    ),
                ),
                runtime_factory=self.factory,
            )
            disabled.initialize()
            self.assertTrue(disabled.run_once())
            self.assertNotIn("printer-0", disabled.runtimes)
            self.assertEqual(
                StateStore(config.connections[0].state_path).load().pending_observation, pending
            )
            resumed = EdgeNode(config, runtime_factory=self.factory)
            resumed.initialize()
            self.assertTrue(resumed.run_once())
            connection = resumed.runtimes["printer-0"]
            self.assertEqual(connection.state.instance_id, runtime.state.instance_id)
            self.assertEqual(connection.cloud.uploads[0], pending)

    def test_cloud_outage_and_restart_preserve_ten_distinct_spool_usage_streams(self) -> None:
        counter = {"length": 0, "duration": 0}

        class PrinterCloud(FakeCloud):
            def __init__(self, index):
                super().__init__()
                self.index = index
                self.fail_upload = False

            def pair(self, **kwargs):
                return PairingResult(f"fhpb_fixture_{self.index}", self.index + 1, self.index + 101)

            def desired_snapshot(self, **kwargs):
                if self.fail_upload:
                    raise HttpRequestError("cloud unavailable")
                return DesiredResult(
                    True,
                    '"revision-1"',
                    {"slots": [{"index": 0, "spool": {"id": self.index + 1001}}]},
                )

        class PrintingProvider(FakeProvider):
            def observe(self):
                return ProviderSnapshot(
                    printer={"state": "printing"},
                    slots=[],
                    slot_topology_complete=False,
                    capabilities=["read", "consumption"],
                    usage={
                        "state": "printing",
                        "file_name": "same-name.gcode",
                        "filament_used_mm": counter["length"],
                        "print_duration_s": counter["duration"],
                        "total_duration_s": counter["duration"],
                    },
                )

        def factory(config, store, state):
            index = int(config.connection_id.rsplit("-", 1)[1])
            return EdgeRuntime(
                config=config,
                store=store,
                state=state,
                provider=PrintingProvider(),
                cloud=PrinterCloud(index),
            )

        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory), 10)
            node = EdgeNode(config, runtime_factory=factory)
            node.initialize()
            self.assertTrue(node.run_once())
            for runtime in node.runtimes.values():
                runtime.cloud.fail_upload = True
            counter.update(length=100, duration=300)
            self.assertFalse(node.run_once())
            pending = {
                key: runtime.state.usage_outbox.copy() for key, runtime in node.runtimes.items()
            }
            self.assertTrue(all(len(batches) == 1 for batches in pending.values()))

            resumed = EdgeNode(config, runtime_factory=factory)
            resumed.initialize()
            self.assertTrue(resumed.run_once())
            self.assertTrue(resumed.run_once())
            event_ids = set()
            for index in range(10):
                key = f"printer-{index}"
                runtime = resumed.runtimes[key]
                self.assertEqual(runtime.cloud.usage_uploads, pending[key])
                batch = runtime.cloud.usage_uploads[0]
                self.assertEqual(batch["material_system_id"], index + 101)
                self.assertEqual(batch["source_instance_id"], runtime.state.instance_id)
                event = batch["events"][0]
                self.assertEqual(
                    event["items"],
                    [{"slot_index": 0, "spool_id": index + 1001, "used_length_mm": 100.0}],
                )
                event_ids.add(event["event_id"])
                self.assertEqual(
                    StateStore(config.connections[index].state_path).load().usage_outbox, []
                )
            self.assertEqual(len(event_ids), 10)

    def test_full_queue_is_durable_and_only_stops_its_connection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            node = EdgeNode(self.config(Path(directory)), runtime_factory=self.factory)
            node.initialize()
            self.assertTrue(node.run_once())
            runtime = node.runtimes["printer-0"]
            runtime.state.last_usage_batch_sequence = 1
            runtime.state.usage_outbox = [{"sequence": 1, "events": [{"event_id": "queued"}]}]
            runtime.store.save(runtime.state)
            runtime.cloud.fail_upload = True
            with patch("filamenthub_edge.runtime.MAX_USAGE_OUTBOX_BATCHES", 1):
                self.assertFalse(node.run_once())
            self.assertEqual(node.errors, {"printer-0": "StateError"})
            self.assertEqual(runtime.store.load().usage_outbox, runtime.state.usage_outbox)
            self.assertEqual(len(node.runtimes["printer-1"].cloud.uploads), 2)

    def test_reset_creates_a_new_event_stream_without_resetting_node_or_other_printers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            node = EdgeNode(self.config(Path(directory)), runtime_factory=self.factory)
            node.initialize()
            self.assertTrue(node.run_once())
            first = node.runtimes["printer-0"]
            second_before = node.runtimes["printer-1"].store.path.read_bytes()
            node.reset_connection("printer-0")
            reset = first.store.load()
            self.assertNotEqual(reset.instance_id, first.state.instance_id)
            self.assertEqual(reset.node_instance_id, node.node_instance_id)
            self.assertIsNone(reset.bridge_token)
            self.assertEqual(reset.last_usage_batch_sequence, 0)
            self.assertEqual(node.runtimes["printer-1"].store.path.read_bytes(), second_before)

    def test_stop_checkpoints_known_usage_without_waiting_on_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            node = EdgeNode(self.config(Path(directory)), runtime_factory=self.factory)
            node.initialize()
            self.assertTrue(node.run_once())
            for runtime in node.runtimes.values():
                runtime.state.usage_tracker = {
                    "job_id": runtime.state.instance_id + ":job",
                    "file_name": "part.gcode",
                    "started_at": "2026-08-30T00:00:00+00:00",
                    "last_state": "printing",
                    "last_print_duration_s": 100,
                    "pending_length_mm": 50,
                    "route": {"slot_index": 0, "spool_id": 99},
                    "terminal_emitted": False,
                }
                runtime.store.save(runtime.state)
            stop = threading.Event()
            stop.set()
            with patch.object(
                FakeProvider, "observe", side_effect=AssertionError("No stop-time I/O")
            ):
                node.run_forever(stop)
            for runtime in node.runtimes.values():
                persisted = runtime.store.load()
                self.assertEqual(persisted.usage_outbox[0]["events"][0]["reasons"], ["shutdown"])
                self.assertEqual(
                    persisted.usage_outbox[0]["events"][0]["items"][0]["used_length_mm"], 50
                )
                self.assertEqual(runtime.cloud.usage_uploads, [])


class NodeConfigTest(unittest.TestCase):
    def test_unsafe_ids_duplicate_endpoints_and_unbounded_lists_are_rejected(self) -> None:
        first = {"id": "one", "moonraker_url": "http://printer.test"}
        invalid = [
            [{**first, "id": "../escape"}],
            [first, {**first, "id": "two", "moonraker_url": "http://printer.test:80"}],
            [first, {**first, "moonraker_url": "http://another.test"}],
            [first] * (MAX_CONNECTIONS + 1),
            [{**first, "unexpected_option": "must not be ignored"}],
        ]
        for entries in invalid:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "options.json"
                path.write_text(json.dumps({"connections": entries}), encoding="utf-8")
                with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
                    with self.assertRaises(ConfigurationError):
                        NodeConfig.load()

    def test_explicit_missing_or_oversized_configuration_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
                with self.assertRaisesRegex(ConfigurationError, "not found"):
                    NodeConfig.load()
                path.write_text(" " * (MAX_OPTIONS_BYTES + 1), encoding="utf-8")
                with self.assertRaisesRegex(ConfigurationError, "too large"):
                    NodeConfig.load()
