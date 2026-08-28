from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from filamenthub_edge.cloud import DesiredResult, PairingResult
from filamenthub_edge.config import EdgeConfig
from filamenthub_edge.errors import HttpRequestError
from filamenthub_edge.providers.base import ProviderSnapshot
from filamenthub_edge.runtime import EdgeRuntime
from filamenthub_edge.state import StateStore


class FakeCloud:
    def __init__(self) -> None:
        self.fail_upload = True
        self.pair_calls = 0
        self.uploads: list[dict] = []
        self.usage_uploads: list[dict] = []
        self.heartbeats: list[dict] = []

    def pair(self, **kwargs) -> PairingResult:  # noqa: ANN003
        self.pair_calls += 1
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
    def __init__(self, snapshots: list[ProviderSnapshot]) -> None:
        self.snapshots = snapshots

    def observe(self) -> ProviderSnapshot:
        return self.snapshots.pop(0)

    def capabilities(self) -> list[str]:
        return ["read", "presence", "consumption"]


class EdgeRuntimeTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
