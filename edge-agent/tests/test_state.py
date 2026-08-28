from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filamenthub_edge.errors import StateError
from filamenthub_edge.state import EdgeState, StateStore


class StateStoreTest(unittest.TestCase):
    def test_save_fsyncs_state_before_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            store = StateStore(state_path)

            with patch("filamenthub_edge.state.os.fsync", wraps=os.fsync) as fsync:
                store.save(EdgeState())

            expected_calls = 2 if os.name == "posix" else 1
            self.assertEqual(fsync.call_count, expected_calls)
            self.assertEqual(store.load().instance_id[:5], "edge-")

    def test_pending_sequence_must_match_durable_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            state = EdgeState(
                physical_printer_id=10,
                material_system_id=20,
                last_snapshot_sequence=2,
                pending_observation={"sequence": 2},
            )
            store = StateStore(state_path)
            store.save(state)
            decoded = json.loads(state_path.read_text(encoding="utf-8"))
            decoded["pending_observation"]["sequence"] = 1
            state_path.write_text(json.dumps(decoded), encoding="utf-8")
            if os.name == "posix":
                state_path.chmod(0o600)

            with self.assertRaisesRegex(StateError, "sequence"):
                store.load()

    def test_usage_outbox_requires_strictly_ordered_durable_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            store = StateStore(state_path)
            store.save(
                EdgeState(
                    physical_printer_id=10,
                    material_system_id=20,
                    last_usage_batch_sequence=2,
                    usage_outbox=[
                        {"sequence": 2, "events": [{"event_id": "event-2"}]},
                    ],
                )
            )
            decoded = json.loads(state_path.read_text(encoding="utf-8"))
            decoded["usage_outbox"].append(
                {"sequence": 1, "events": [{"event_id": "event-1"}]}
            )
            state_path.write_text(json.dumps(decoded), encoding="utf-8")
            if os.name == "posix":
                state_path.chmod(0o600)

            with self.assertRaisesRegex(StateError, "outbox"):
                store.load()

    def test_pairing_and_retry_state_require_a_complete_binding(self) -> None:
        invalid_states = [
            EdgeState(bridge_token="fhpb_fixture"),
            EdgeState(physical_printer_id=10),
            EdgeState(
                physical_printer_id=10,
                material_system_id=20,
                pairing_code_digest="not-a-sha256-digest",
            ),
            EdgeState(pending_observation={"sequence": 0}),
            EdgeState(
                last_usage_batch_sequence=1,
                usage_outbox=[{"sequence": 1, "events": [{"event_id": "event-1"}]}],
            ),
        ]

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "edge-state.json")
            for state in invalid_states:
                with self.subTest(state=state):
                    store.save(state)
                    with self.assertRaises(StateError):
                        store.load()

    def test_oversized_outbox_is_rejected_before_state_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "edge-state.json"
            store = StateStore(state_path)

            with patch("filamenthub_edge.state.MAX_STATE_BYTES", 128):
                with self.assertRaisesRegex(StateError, "size"):
                    store.save(EdgeState(usage_tracker={"payload": "x" * 256}))

            self.assertFalse(state_path.exists())

    @unittest.skipUnless(os.name == "posix", "POSIX ownership and mode contract")
    def test_state_and_directory_permissions_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory) / "edge"
            state_path = state_directory / "edge-state.json"
            store = StateStore(state_path)

            store.save(EdgeState())

            self.assertEqual(stat.S_IMODE(state_directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX ownership and mode contract")
    def test_unsafe_custom_state_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory) / "shared"
            state_directory.mkdir(mode=0o755)
            state_directory.chmod(0o755)
            store = StateStore(state_directory / "edge-state.json")

            with self.assertRaisesRegex(StateError, "permissions"):
                store.load()
            with self.assertRaisesRegex(StateError, "permissions"):
                store.save(EdgeState())


if __name__ == "__main__":
    unittest.main()
