"""A broken scenario must not look like a printer counter reset."""

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import moonraker_hh as lab


class MoonrakerScenarioTest(unittest.TestCase):
    def test_live_scenario_keeps_identity_and_rejects_broken_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "moonraker-state.json"
            with patch.object(lab, "STATE_FILE", path):
                server = ThreadingHTTPServer(("127.0.0.1", 0), lab.MoonrakerHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                origin = f"http://127.0.0.1:{server.server_port}"

                def request(endpoint, payload=None):
                    req = Request(
                        origin + endpoint,
                        data=json.dumps(payload).encode() if payload is not None else None,
                        headers={"X-Api-Key": lab.API_KEY},
                    )
                    with urlopen(req, timeout=2) as response:
                        return json.load(response)["result"]

                try:
                    query = {"objects": {"mmu": None, "print_stats": None}}
                    default = request("/printer/objects/query", query)["status"]
                    self.assertEqual(default["print_stats"]["state"], "standby")
                    identity = request("/server/database/item?namespace=moonraker&key=instance_id")
                    for counter, state in [(0, "printing"), (1000, "paused"), (1200, "complete")]:
                        path.write_text(json.dumps({
                            "print_stats": {"state": state, "filament_used": counter},
                            "mmu": {"gate": 0, "tool": 0, "spoolman_support": "off"},
                            "spoolman_url": None,
                        }), encoding="utf-8")
                        actual = request("/printer/objects/query", query)["status"]
                        self.assertEqual(actual["print_stats"]["filament_used"], counter)
                        self.assertEqual(actual["print_stats"]["state"], state)
                        self.assertEqual(actual["mmu"]["num_gates"], 4)
                        self.assertEqual(request("/server/config")["config"], {})
                        self.assertEqual(
                            request("/server/database/item?namespace=moonraker&key=instance_id"),
                            identity,
                        )
                    for broken in ("{", "[]", '{"print_stats": null}', " " * 65537):
                        path.write_text(broken, encoding="utf-8")
                        with self.assertRaises(HTTPError) as error:
                            request("/printer/objects/query", query)
                        self.assertEqual(error.exception.code, 503)
                    self.assertEqual(lab.PRINT_STATS["filament_used"], 0)
                    self.assertEqual(lab.MMU_STATE["gate"], -2)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
