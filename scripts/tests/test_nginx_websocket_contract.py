import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NGINX_CONFIG = ROOT / "frontend" / "nginx.conf"
SITE_CONFIG = ROOT / "frontend" / "site-common.conf"
DEV_CONFIG = ROOT / "frontend" / "nginx.dev.conf"


def _location_body(config: str, location: str) -> str:
    match = re.search(
        rf"(?ms)^    location (?:\^~ )?{re.escape(location)} \{{\n(?P<body>.*?)^    \}}$",
        config,
    )
    if match is None:
        raise AssertionError(f"nginx location {location!r} is missing")
    return match.group("body")


class NginxWebSocketContractTest(unittest.TestCase):
    def test_upgrade_map_preserves_http_keepalive(self) -> None:
        config = NGINX_CONFIG.read_text(encoding="utf-8")

        match = re.search(
            r"(?ms)^map \$http_upgrade \$filamenthub_connection_upgrade \{\n"
            r"(?P<body>.*?)^\}$",
            config,
        )
        self.assertIsNotNone(match, "conditional WebSocket Connection map is missing")
        body = match.group("body") if match is not None else ""
        self.assertRegex(body, r"(?m)^    default upgrade;$")
        self.assertRegex(body, r'(?m)^    "" "";$')

    def test_public_spoolman_paths_forward_websocket_handshake(self) -> None:
        for config_path in (SITE_CONFIG, DEV_CONFIG):
            config = config_path.read_text(encoding="utf-8")
            for location in ("/api", "/spool_compat"):
                with self.subTest(config=config_path.name, location=location):
                    self.assertRegex(
                        config,
                        rf"(?m)^    location \^~ {re.escape(location)} \{{$",
                    )
                    body = _location_body(config, location)
                    self.assertIn("proxy_http_version 1.1;", body)
                    self.assertIn("proxy_set_header Upgrade $http_upgrade;", body)
                    self.assertIn(
                        "proxy_set_header Connection "
                        + ("$filamenthub_connection_upgrade;" if config_path == SITE_CONFIG else "'upgrade';"),
                        body,
                    )
                    if config_path == SITE_CONFIG:
                        self.assertNotIn('proxy_set_header Connection "";', body)


if __name__ == "__main__":
    unittest.main()
