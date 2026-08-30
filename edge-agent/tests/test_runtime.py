from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from filamenthub_edge.cloud import DesiredResult, PairingResult
from filamenthub_edge.config import EdgeConfig
from filamenthub_edge.errors import (
    HttpRequestError,
    IdentityConflict,
    ProviderUnavailable,
    StateError,
)
from filamenthub_edge.providers.base import ProviderSnapshot
from filamenthub_edge.runtime import EdgeRuntime
from filamenthub_edge.state import StateStore


class FakeCloud:
    def __init__(self) -> None:
        self.fail_upload = True
        self.fail_revoke = False
        self.pair_calls = 0
        self.pair_payloads: list[dict] = []
        self.uploads: list[dict] = []
        self.usage_uploads: list[dict] = []
        self.heartbeats: list[dict] = []
        self.revoked_tokens: list[str] = []

    def pair(self, **kwargs) -> PairingResult:  # noqa: ANN003
        self.pair_calls += 1
        self.pair_payloads.append(kwargs)
        return PairingResult("fhpb_fixture", 10, 20)

    def desired_snapshot(self, **kwargs) -> DesiredResult:  # noqa: ANN003
        return DesiredResult(
            True,
            '"revision-1"',
            {
                "revision": "revision-1",
                "physical_printer_id": 10,
                "material_system_id": 20,
                "system_name": "Happy Hare",
                "system_kind": "mmu",
                "slots": [{"index": 0, "spool": {"id": 99}}],
            },
        )

    def upload_observation(self, **kwargs) -> None:  # noqa: ANN003
        if self.fail_upload:
            raise HttpRequestError("cloud unavailable")
        self.uploads.append(kwargs["payload"])

    def upload_usage_batch(self, **kwargs) -> None:  # noqa: ANN003
        if self.fail_upload:
            raise HttpRequestError("cloud unavailable")
        self.usage_uploads.append(kwargs["payload"])

    def heartbeat(self, **kwargs) -> None:  # noqa: ANN003
        self.heartbeats.append(kwargs["payload"])

    def revoke(self, **kwargs) -> None:  # noqa: ANN003
        if self.fail_revoke:
            raise HttpRequestError("cloud unavailable")
        self.revoked_tokens.append(kwargs["token"])


class FakeProvider:
    def observe(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            printer={"state": "idle"},
            slots=[{"provider_index": 0, "present": True}],
            slot_topology_complete=True,
            capabilities=["read", "presence"],
        )

    def capabilities(self) -> list[str]:
        return ["read", "presence"]


class SequenceProvider:
    def __init__(self, snapshots: list[ProviderSnapshot | Exception]) -> None:
        self.snapshots = snapshots

    def observe(self) -> ProviderSnapshot:
        value = self.snapshots.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def capabilities(self) -> list[str]:
        return ["read", "presence", "consumption"]


class EdgeRuntimeTest(unittest.TestCase):
    def test_replaced_device_cannot_debit_usage_and_rejected_queue_recovers(self) -> None:
        class IdentityCloud(FakeCloud):
            def upload_observation(self, **kwargs):
                identity = kwargs["payload"].get("device_identity")
                if self.uploads and identity != self.uploads[0].get("device_identity"):
                    raise IdentityConflict("different device", status_code=409)
                return super().upload_observation(**kwargs)

        def snapshot(identity, used):
            return ProviderSnapshot(
                printer={"state": "printing"},
                slots=[{"provider_index": 0, "active_feed": True}],
                slot_topology_complete=True,
                capabilities=["read", "consumption"],
                device_identity=("moonraker_instance", identity),
                usage={
                    "state": "printing",
                    "file_name": "same-name.gcode",
                    "filament_used_mm": used,
                    "print_duration_s": used,
                    "total_duration_s": used,
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge-state.json"
            store = StateStore(path)
            state = store.load()
            state.bridge_token, state.physical_printer_id, state.material_system_id = (
                "fhpb_fixture",
                10,
                20,
            )
            state.printer_discovery_key = "ab" * 32
            cloud = IdentityCloud()
            cloud.fail_upload = False
            runtime = EdgeRuntime(
                config=self._config(path),
                cloud=cloud,
                store=store,
                state=state,
                provider=SequenceProvider(
                    [
                        snapshot("a" * 32, 0),
                        snapshot("b" * 32, 5000),
                        snapshot("b" * 32, 6000),
                        snapshot("a" * 32, 100),
                    ]
                ),
            )
            runtime.run_cycle()
            baseline = dict(state.usage_tracker)
            with self.assertRaises(IdentityConflict):
                runtime.run_cycle()
            self.assertEqual(state.usage_tracker, baseline)
            self.assertEqual(cloud.usage_uploads, [])
            self.assertIsNone(store.load().pending_observation)
            self.assertIsNotNone(store.load().rejected_observation)
            runtime.shutdown()
            self.assertEqual(cloud.usage_uploads, [])
            runtime.run_cycle()
            self.assertIsNone(store.load().rejected_observation)
            self.assertEqual(state.usage_tracker["last_filament_used_mm"], 100)

    def test_stale_observation_cannot_confirm_a_new_device(self) -> None:
        class StaleCloud(FakeCloud):
            def upload_observation(self, **kwargs):
                return False

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge-state.json"
            store = StateStore(path)
            state = store.load()
            state.bridge_token, state.physical_printer_id, state.material_system_id = (
                "fhpb_fixture",
                10,
                20,
            )
            state.printer_discovery_key = "ab" * 32
            snapshot = replace(
                FakeProvider().observe(), device_identity=("moonraker_instance", "a" * 32)
            )
            runtime = EdgeRuntime(
                config=self._config(path),
                cloud=StaleCloud(),
                store=store,
                state=state,
                provider=SequenceProvider([snapshot]),
            )
            with self.assertRaises(ProviderUnavailable):
                runtime.run_cycle()
            self.assertIsNone(state.confirmed_device_identity)
            self.assertIsNone(state.usage_tracker)

    @staticmethod
    def _config(state_path: Path) -> EdgeConfig:
        return EdgeConfig(
            filamenthub_url="http://filamenthub.test",
            pairing_code="FH-AAAAA-BBBBB",
            material_provider="happy_hare",
            moonraker_url="http://moonraker.test",
            moonraker_api_key=None,
            state_path=state_path,
            sync_interval=30,
            request_timeout=2,
            allow_insecure_cloud=True,
            run_once=True,
        )

    def test_pending_observation_survives_restart_and_is_flushed_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            store = StateStore(state_path)
            runtime = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=FakeProvider(),
                store=store,
                state=store.load(),
            )

            with self.assertRaises(HttpRequestError):
                runtime.run_cycle()

            persisted = store.load()
            self.assertIsNotNone(persisted.bridge_token)
            self.assertIsNotNone(persisted.desired_snapshot)
            self.assertIsNotNone(persisted.pending_observation)
            first_observed_at = persisted.pending_observation["observed_at"]
            self.assertEqual(persisted.pending_observation["sequence"], 1)
            self.assertEqual(persisted.last_snapshot_sequence, 1)

            cloud.fail_upload = False
            restarted = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=FakeProvider(),
                store=store,
                state=persisted,
            )
            restarted.run_cycle()

            self.assertEqual(cloud.pair_calls, 1)
            self.assertEqual(len(cloud.uploads), 2)
            self.assertEqual(cloud.uploads[0]["observed_at"], first_observed_at)
            self.assertEqual(cloud.uploads[0]["sequence"], 1)
            self.assertEqual(cloud.uploads[1]["sequence"], 2)
            self.assertIsNone(store.load().pending_observation)
            self.assertEqual(store.load().last_snapshot_sequence, 2)
            self.assertEqual(len(cloud.heartbeats), 1)

    def test_usage_batches_survive_cloud_outage_and_flush_in_order(self) -> None:
        def provider_snapshot(state: str, used: float, duration: float) -> ProviderSnapshot:
            return ProviderSnapshot(
                printer={"state": state},
                slots=[{"provider_index": 0, "active_feed": True}],
                slot_topology_complete=True,
                capabilities=["read", "presence", "consumption"],
                usage={
                    "state": state,
                    "file_name": "offline.gcode",
                    "filament_used_mm": used,
                    "print_duration_s": duration,
                    "total_duration_s": duration,
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            cloud.fail_upload = False
            store = StateStore(state_path)
            provider = SequenceProvider(
                [
                    provider_snapshot("printing", 0, 0),
                    provider_snapshot("printing", 120, 300),
                    provider_snapshot("complete", 150, 330),
                    provider_snapshot("complete", 150, 330),
                ]
            )

            EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=provider,
                store=store,
                state=store.load(),
            ).run_cycle()

            cloud.fail_upload = True
            offline = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=provider,
                store=store,
                state=store.load(),
            )
            with self.assertRaises(HttpRequestError):
                offline.run_cycle()
            with self.assertRaises(HttpRequestError):
                offline.run_cycle()

            persisted = store.load()
            self.assertEqual([batch["sequence"] for batch in persisted.usage_outbox], [1, 2])
            first_event_id = persisted.usage_outbox[0]["events"][0]["event_id"]
            self.assertTrue(first_event_id.endswith(":1:1"))
            self.assertEqual(persisted.usage_outbox[1]["events"][0]["outcome"], "completed")
            self.assertIsNotNone(persisted.pending_observation)

            cloud.fail_upload = False
            EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=provider,
                store=store,
                state=persisted,
            ).run_cycle()

            self.assertEqual([batch["sequence"] for batch in cloud.usage_uploads], [1, 2])
            self.assertEqual(store.load().usage_outbox, [])
            self.assertIsNone(store.load().pending_observation)

    def test_rotation_preserves_binding_and_idle_reset_revokes_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            cloud.fail_upload = False
            store = StateStore(state_path)
            state = store.load()
            state.physical_printer_id = 10
            state.material_system_id = 20
            store.save(state)
            runtime = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=FakeProvider(),
                store=store,
                state=state,
            )

            runtime.run_cycle()

            self.assertEqual(cloud.pair_payloads[0]["previous_physical_printer_id"], 10)
            self.assertEqual(cloud.pair_payloads[0]["previous_material_system_id"], 20)
            status = runtime.diagnostic_status()
            self.assertTrue(status["paired"])
            self.assertNotIn("fhpb_fixture", str(status))

            runtime.reset_connection()

            reset_state = store.load()
            self.assertEqual(cloud.revoked_tokens, ["fhpb_fixture"])
            self.assertIsNone(reset_state.bridge_token)
            self.assertIsNone(reset_state.physical_printer_id)
            self.assertIsNone(reset_state.material_system_id)
            self.assertIsNone(reset_state.desired_snapshot)
            self.assertEqual(reset_state.last_snapshot_sequence, 0)

    def test_reset_refuses_to_discard_durable_usage_or_active_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            store = StateStore(state_path)
            state = store.load()
            state.bridge_token = "fhpb_fixture"
            state.physical_printer_id = 10
            state.material_system_id = 20
            state.last_usage_batch_sequence = 1
            state.usage_outbox = [{"sequence": 1, "events": [{"event_id": "event-1"}]}]
            state.usage_tracker = {"terminal_emitted": False}
            store.save(state)
            runtime = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=FakeProvider(),
                store=store,
                state=state,
            )

            with self.assertRaisesRegex(StateError, "usage outbox, active usage tracker"):
                runtime.reset_connection()

            self.assertEqual(cloud.revoked_tokens, [])
            self.assertEqual(store.load().usage_outbox[0]["sequence"], 1)

    def test_reset_keeps_binding_when_cloud_revoke_is_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            cloud.fail_revoke = True
            store = StateStore(state_path)
            state = store.load()
            state.bridge_token = "fhpb_fixture"
            state.physical_printer_id = 10
            state.material_system_id = 20
            store.save(state)
            runtime = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=FakeProvider(),
                store=store,
                state=state,
            )

            with self.assertRaises(HttpRequestError):
                runtime.reset_connection()

            persisted = store.load()
            self.assertEqual(persisted.bridge_token, "fhpb_fixture")
            self.assertEqual(persisted.physical_printer_id, 10)
            self.assertEqual(persisted.material_system_id, 20)

    def test_provider_disconnect_and_shutdown_flush_safe_checkpoints(self) -> None:
        def provider_snapshot(used: float, duration: float) -> ProviderSnapshot:
            return ProviderSnapshot(
                printer={"state": "printing"},
                slots=[{"provider_index": 0, "active_feed": True}],
                slot_topology_complete=True,
                capabilities=["read", "presence", "consumption"],
                usage={
                    "state": "printing",
                    "file_name": "lifecycle.gcode",
                    "filament_used_mm": used,
                    "print_duration_s": duration,
                    "total_duration_s": duration,
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = self._config(state_path)
            cloud = FakeCloud()
            cloud.fail_upload = False
            store = StateStore(state_path)
            provider = SequenceProvider(
                [
                    provider_snapshot(0, 0),
                    provider_snapshot(40, 40),
                    ProviderUnavailable("moonraker offline"),
                    provider_snapshot(70, 70),
                ]
            )
            runtime = EdgeRuntime(
                config=config,
                cloud=cloud,
                provider=provider,
                store=store,
                state=store.load(),
            )
            runtime.run_cycle()
            runtime.run_cycle()

            with self.assertRaises(ProviderUnavailable):
                runtime.run_cycle()
            self.assertEqual(
                cloud.usage_uploads[-1]["events"][0]["reasons"],
                ["disconnect"],
            )
            self.assertEqual(
                cloud.usage_uploads[-1]["events"][0]["items"][0]["used_length_mm"],
                40,
            )

            runtime.shutdown()

            self.assertEqual(
                cloud.usage_uploads[-1]["events"][0]["reasons"],
                ["shutdown"],
            )
            self.assertEqual(
                cloud.usage_uploads[-1]["events"][0]["items"][0]["used_length_mm"],
                30,
            )
            self.assertEqual(store.load().usage_outbox, [])


if __name__ == "__main__":
    unittest.main()
