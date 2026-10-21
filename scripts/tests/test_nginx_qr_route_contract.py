import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SITE_CONFIG = ROOT / "frontend" / "site-common.conf"
QR_LOCATION = re.compile(r'(?ms)^    location ~ "(?P<pattern>\^/qr/[^"]+)" \{\n(?P<body>.*?)^    \}$')


def _qr_location() -> re.Match[str]:
    match = QR_LOCATION.search(SITE_CONFIG.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError("nginx location for printed /qr/<code> links is missing")
    return match


class NginxQrRouteContractTest(unittest.TestCase):
    def test_printed_qr_link_reaches_backend_redirect(self) -> None:
        body = _qr_location().group("body")

        self.assertIn("rewrite ^ /api/v1/qr/$filamenthub_qr_code break;", body)
        self.assertIn("proxy_pass http://filamenthub_backend;", body)
        self.assertIn("proxy_set_header X-FilamentHub-Client-IP $remote_addr;", body)
        # A cached redirect would stop counting scans.
        self.assertNotIn("proxy_cache", body)

    def test_only_the_short_code_path_is_routed(self) -> None:
        nginx_pattern = _qr_location().group("pattern")
        pattern = re.compile(nginx_pattern.replace("(?<", "(?P<"))

        for path in ("/qr/FH-000-001", "/qr/FH-000-001/", "/qr/FHQ1_01_X_U_abcdefghijklmnop"):
            with self.subTest(path=path):
                self.assertIsNotNone(pattern.match(path))

        for path in ("/qr_codes/FH-000-001.png", "/qr/FH-000-001/image", "/qr/", "/qr/a.b"):
            with self.subTest(path=path):
                self.assertIsNone(pattern.match(path))


if __name__ == "__main__":
    unittest.main()
