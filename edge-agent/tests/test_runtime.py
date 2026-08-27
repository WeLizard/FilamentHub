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


class EdgeRuntimeTest(unittest.TestCase):
    def test_pending_observation_survives_restart_and_is_flushed_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            config = EdgeConfig(
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
            self.assertIsNone(store.load().pending_observation)
            self.assertEqual(len(cloud.heartbeats), 1)


if __name__ == "__main__":
    unittest.main()
