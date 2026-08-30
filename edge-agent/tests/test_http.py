from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from filamenthub_edge.cloud import FilamentHubCloud
from filamenthub_edge.config import NodeConfig
from filamenthub_edge.errors import ConfigurationError, HttpRequestError
from filamenthub_edge.http import normalize_origin


class NormalizeOriginTest(unittest.TestCase):
    def test_usage_ack_must_match_sequence_and_every_event_before_queue_removal(self) -> None:
        cloud = FilamentHubCloud("https://filamenthub.test", timeout=2, allow_insecure_http=False)
        payload = {"sequence": 1, "events": [{"event_id": "one"}, {"event_id": "two"}]}
        valid = {
            "accepted": True,
            "ack_sequence": 1,
            "events": [{"event_id": "one"}, {"event_id": "two"}],
        }
        invalid = [
            {**valid, "ack_sequence": True},
            {**valid, "ack_sequence": 2},
            {**valid, "events": []},
            {**valid, "events": [{"event_id": "one"}]},
            {**valid, "events": [{"event_id": "two"}, {"event_id": "one"}]},
        ]
        for response in invalid:
            with (
                self.subTest(response=response),
                patch.object(cloud, "_authorized_request", return_value=(200, response, {})),
            ):
                with self.assertRaises(HttpRequestError):
                    cloud.upload_usage_batch(token="fhpb_fixture", payload=payload)
        with patch.object(cloud, "_authorized_request", return_value=(200, valid, {})):
            cloud.upload_usage_batch(token="fhpb_fixture", payload=payload)

    def test_cloud_origin_requires_https_by_default(self) -> None:
        with self.assertRaises(ConfigurationError):
            normalize_origin("http://filamenthub.test", allow_http=False)

    def test_credentials_and_paths_are_rejected(self) -> None:
        for value in (
            "https://user:secret@filamenthub.test",
            "https://filamenthub.test/private",
            "https://filamenthub.test?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                normalize_origin(value, allow_http=False)

    def test_api_prefix_is_normalized_to_the_same_origin(self) -> None:
        self.assertEqual(
            normalize_origin("https://filamenthub.test/api/v1", allow_http=False),
            "https://filamenthub.test",
        )

    def test_home_assistant_options_feed_the_same_runtime_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            options_path = Path(directory) / "options.json"
            options_path.write_text(
                """{
                    "filamenthub_url": "https://filamenthub.test",
                    "connections": [{
                        "id": "workshop",
                        "pairing_code": "FH-AAAAA-BBBBB",
                        "material_provider": "happy_hare",
                        "moonraker_url": "http://moonraker.local:7125",
                        "moonraker_api_key": "local-key"
                    }],
                    "sync_interval": 45,
                    "allow_insecure_cloud": false
                }""",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {
                    "FH_EDGE_OPTIONS_FILE": str(options_path),
                    "FH_EDGE_STATE_DIRECTORY": directory,
                },
                clear=True,
            ):
                config = NodeConfig.load()

        self.assertEqual(config.filamenthub_url, "https://filamenthub.test")
        connection = config.connections[0]
        self.assertEqual(connection.moonraker_url, "http://moonraker.local:7125")
        self.assertEqual(connection.sync_interval, 45)
        self.assertEqual(connection.pairing_code, "FH-AAAAA-BBBBB")
        self.assertNotIn("local-key", repr(config))


if __name__ == "__main__":
    unittest.main()
