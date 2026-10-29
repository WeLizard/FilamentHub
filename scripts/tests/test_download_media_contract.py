import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SITE_CONFIG = ROOT / "frontend" / "site-common.conf"
COMPOSE = ROOT / "docker-compose.yml"
CONSOLE = ROOT / "scripts" / "deploy-server.ps1"
MOUNT = "/usr/share/nginx/download-media"


class DownloadMediaContractTest(unittest.TestCase):
    def test_videos_are_served_from_the_mounted_directory(self) -> None:
        config = SITE_CONFIG.read_text(encoding="utf-8")
        media = config.find('location ~ "^/download-media/')
        static = config.find("location ~* \\.(js|css")

        self.assertNotEqual(media, -1, "nginx location for download-page videos is missing")
        # nginx picks the first matching regex: below the static rule the videos
        # would be looked up inside the image, where Git never puts them.
        self.assertLess(media, static)
        self.assertIn(f"alias {MOUNT}/$filamenthub_media_file;", config[media:static])

    def test_only_the_two_overview_videos_are_exposed(self) -> None:
        config = SITE_CONFIG.read_text(encoding="utf-8")
        nginx_pattern = re.search(r'location ~ "(\^/download-media/[^"]+)"', config).group(1)
        pattern = re.compile(nginx_pattern.replace("(?<", "(?P<"))

        for name in ("filamenthub-overview-ru.mp4", "filamenthub-overview-en.mp4"):
            self.assertIsNotNone(pattern.match(f"/download-media/{name}"))
        for path in (
            "/download-media/filamenthub-overview-ru.vtt",
            "/download-media/filamenthub-overview-de.mp4",
            "/download-media/../filamenthub-overview-ru.mp4",
        ):
            self.assertIsNone(pattern.match(path))

    def test_frontend_mounts_media_read_only_and_one_time_upload_is_explicit(self) -> None:
        self.assertIn(f"- ./media/download:{MOUNT}:ro", COMPOSE.read_text(encoding="utf-8"))

        console = CONSOLE.read_text(encoding="utf-8")
        self.assertIn('$remoteDirectory = "$RemoteProjectDirectory/media/download"', console)
        self.assertIn(f"grep -Fx '{MOUNT}'", console)
        self.assertIn("-w '$remoteDirectory'", console)
        self.assertIn("создай '$remoteDirectory' на VDS", console)
        self.assertIn("назначь SSH-пользователя владельцем '$remoteDirectory'", console)
        self.assertIn("FH_MEDIA_DIR_NOT_WRITABLE", console)
        self.assertIn("-Action PublishDownloadMedia", console)
        self.assertIn("sha256sum -c -", console)
        self.assertIn("'PublishDownloadMedia' { Publish-DownloadMedia }", console)

        production_menu = console.split("function Show-ProductionMenu", maxsplit=1)[1].split(
            "function Show-PluginMenu", maxsplit=1
        )[0]
        self.assertNotIn("Залить ролики страницы «Скачать»", production_menu)
        self.assertNotIn("'7' { Publish-DownloadMedia }", production_menu)

    def test_runtime_media_is_outside_git_and_never_blocks_a_deploy(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(gitignore, r"(?m)^/media/$")

        deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
        clean_check = deploy.split('dirty="$(git status', 1)[1].split(
            '[[ -z "$dirty" ]]', 1
        )[0]
        self.assertIn("':(exclude)media'", clean_check)
        self.assertIn("':(exclude)media/**'", clean_check)


if __name__ == "__main__":
    unittest.main()
