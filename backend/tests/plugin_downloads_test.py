"""The download page serves plugin packages from our own server, not from GitHub."""

import hashlib

import httpx
import pytest

from app.services import plugin_release_service as service

ORCA_WHEEL = "filamenthub-0.0.8-py3-none-any.whl"
BRIDGE_WHEEL = "octoprint_filamenthubbridge-0.1.0-py3-none-any.whl"
PRINT_FARM_WHEEL = "printers-0.0.4-py3-none-any.whl"
ORCA_BYTES = b"orca-wheel-bytes"
BRIDGE_BYTES = b"bridge-wheel-bytes"
PRINT_FARM_BYTES = b"print-farm-wheel-bytes"


def _checksums() -> str:
    return (
        f"{hashlib.sha256(ORCA_BYTES).hexdigest()}  ./{ORCA_WHEEL}\n"
        f"{hashlib.sha256(BRIDGE_BYTES).hexdigest()}  ./{BRIDGE_WHEEL}\n"
    )


def _release(*, draft: bool = False, tag: str = "plugins-v0.1.0") -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "html_url": f"https://github.com/WeLizard/FilamentHub/releases/tag/{tag}",
        "assets": [
            {
                "name": ORCA_WHEEL,
                "size": len(ORCA_BYTES),
                "browser_download_url": f"https://example.invalid/{ORCA_WHEEL}",
            },
            {
                "name": BRIDGE_WHEEL,
                "size": len(BRIDGE_BYTES),
                "browser_download_url": f"https://example.invalid/{BRIDGE_WHEEL}",
            },
            {
                "name": "octoprint_filamenthubbridge-0.1.0.tar.gz",
                "size": 11942,
                "browser_download_url": "https://example.invalid/sdist.tar.gz",
            },
            {
                "name": "SHA256SUMS",
                "size": 331,
                "browser_download_url": "https://example.invalid/SHA256SUMS",
            },
        ],
    }


def _print_farm_release(*, draft: bool = False) -> dict:
    return {
        "tag_name": "printers-v0.0.4",
        "draft": draft,
        "html_url": "https://github.com/WeLizard/orca-plugins/releases/tag/printers-v0.0.4",
        "assets": [
            {
                "name": PRINT_FARM_WHEEL,
                "size": len(PRINT_FARM_BYTES),
                "browser_download_url": f"https://example.invalid/{PRINT_FARM_WHEEL}",
            }
        ],
    }


class _Transport(httpx.AsyncBaseTransport):
    """Answers the two GitHub calls the service makes, and counts them."""

    def __init__(self, releases, *, print_farm_releases=None, files=None):
        self.releases = releases
        self.print_farm_releases = print_farm_releases or []
        self.files = files if files is not None else {
            ORCA_WHEEL: ORCA_BYTES,
            BRIDGE_WHEEL: BRIDGE_BYTES,
            PRINT_FARM_WHEEL: PRINT_FARM_BYTES,
        }
        self.file_requests: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(service.PRINT_FARM_RELEASES_URL):
            return httpx.Response(200, json=self.print_farm_releases, request=request)
        if url.startswith(service.GITHUB_RELEASES_URL):
            return httpx.Response(200, json=self.releases, request=request)
        if url.endswith("SHA256SUMS"):
            return httpx.Response(200, text=_checksums(), request=request)
        name = url.rsplit("/", 1)[-1]
        self.file_requests.append(name)
        payload = self.files.get(name)
        if payload is None:
            return httpx.Response(404, request=request)
        return httpx.Response(200, content=payload, request=request)


class _Unreachable(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("github is unreachable", request=request)


@pytest.fixture(autouse=True)
def isolated_service(tmp_path, monkeypatch):
    """Each test starts with an empty cache and its own mirror directory."""
    monkeypatch.setattr(service, "_cached_packages", [])
    monkeypatch.setattr(service, "_cached_at", None)
    monkeypatch.setattr(service, "_download_locks", {})
    monkeypatch.setattr(service, "mirror_dir", lambda: tmp_path / "plugins")
    yield


def _install(monkeypatch, transport):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return transport


@pytest.mark.asyncio
async def test_published_releases_yield_all_plugin_packages(monkeypatch):
    _install(monkeypatch, _Transport([_release()], print_farm_releases=[_print_farm_release()]))

    packages = await service.get_packages()

    by_plugin = {package.plugin: package for package in packages}
    assert set(by_plugin) == {
        service.ORCASLICER_PLUGIN,
        service.OCTOPRINT_BRIDGE,
        service.PRINT_FARM_PLUGIN,
    }
    assert by_plugin[service.ORCASLICER_PLUGIN].version == "0.0.8"
    assert by_plugin[service.OCTOPRINT_BRIDGE].version == "0.1.0"
    assert by_plugin[service.PRINT_FARM_PLUGIN].version == "0.0.4"
    # The checksum file and the source archive are not offered as downloads.
    assert {package.filename for package in packages} == {
        ORCA_WHEEL,
        BRIDGE_WHEEL,
        PRINT_FARM_WHEEL,
    }
    assert by_plugin[service.OCTOPRINT_BRIDGE].sha256 == hashlib.sha256(BRIDGE_BYTES).hexdigest()


@pytest.mark.asyncio
async def test_a_draft_release_is_never_offered(monkeypatch):
    _install(monkeypatch, _Transport([_release(draft=True)]))

    assert await service.get_packages() == []


@pytest.mark.asyncio
async def test_an_unrelated_release_is_ignored(monkeypatch):
    _install(monkeypatch, _Transport([_release(tag="v2.0.0")]))

    assert await service.get_packages() == []


@pytest.mark.asyncio
async def test_package_is_fetched_once_and_then_served_from_disk(monkeypatch):
    transport = _install(monkeypatch, _Transport([_release()]))
    packages = await service.get_packages()
    bridge = next(item for item in packages if item.plugin == service.OCTOPRINT_BRIDGE)

    first = await service.ensure_local_copy(bridge)
    second = await service.ensure_local_copy(bridge)

    assert first is not None and first.read_bytes() == BRIDGE_BYTES
    assert second == first
    # GitHub is asked for the bytes once; after that our own copy answers.
    assert transport.file_requests == [BRIDGE_WHEEL]


@pytest.mark.asyncio
async def test_a_package_failing_its_checksum_is_not_served(monkeypatch):
    transport = _Transport([_release()], files={BRIDGE_WHEEL: b"tampered"})
    _install(monkeypatch, transport)
    packages = await service.get_packages()
    bridge = next(item for item in packages if item.plugin == service.OCTOPRINT_BRIDGE)

    assert await service.ensure_local_copy(bridge) is None
    assert not (service.mirror_dir() / BRIDGE_WHEEL).exists()


@pytest.mark.asyncio
async def test_a_github_outage_keeps_the_previous_answer(monkeypatch):
    _install(monkeypatch, _Transport([_release()]))
    before = await service.get_packages()
    assert before

    _install(monkeypatch, _Unreachable())
    after = await service.get_packages(force_refresh=True)

    # An empty list would tell people the plugin no longer exists.
    assert after == before


@pytest.mark.asyncio
async def test_the_listing_points_at_our_own_server(client, monkeypatch):
    _install(monkeypatch, _Transport([_release()], print_farm_releases=[_print_farm_release()]))

    response = await client.get("/api/v1/downloads/plugins")

    assert response.status_code == 200
    body = response.json()
    assert {item["plugin"] for item in body["packages"]} == {
        "orcaslicer",
        "octoprint",
        "print_farm",
    }
    for item in body["packages"]:
        assert "api.github.com" not in item["download_url"]
        assert item["download_url"].endswith(f"/api/v1/downloads/plugins/{item['filename']}")
    assert body["release_url"].startswith("https://github.com/")


@pytest.mark.asyncio
async def test_only_names_the_release_published_can_be_downloaded(client, monkeypatch):
    _install(monkeypatch, _Transport([_release()]))

    ok = await client.get(f"/api/v1/downloads/plugins/{BRIDGE_WHEEL}")
    unknown = await client.get("/api/v1/downloads/plugins/anything-else.whl")
    traversal = await client.get("/api/v1/downloads/plugins/..%2F..%2Fapp%2Fmain.py")

    assert ok.status_code == 200
    assert ok.content == BRIDGE_BYTES
    assert unknown.status_code == 404
    assert traversal.status_code == 404
