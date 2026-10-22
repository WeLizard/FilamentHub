"""The operator flow must stop at an editable proposal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cli import catalog_intake


@pytest.mark.asyncio
async def test_build_proposal_reads_sources_and_catalog_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def snapshot(client, name, brand_id):
        calls.append("snapshot")
        assert name == "Maker"
        assert brand_id is None
        return {"filaments": [], "selected_brand": None}

    async def reader(urls, *, max_pages):
        calls.append("source")
        assert urls == ["https://maker.example/catalog"]
        assert max_pages == 1
        return SimpleNamespace(
            model_dump=lambda: {
                "pages": ({"url": urls[0], "text": "PLA", "links": ()},),
                "manifest": {"visited": [urls[0]], "partial": False},
            }
        )

    def batched_proposal(command, bundle, catalog, *, timeout_s):
        calls.append("batched_proposal")
        assert command == ["reasoner {schema} {output}"]
        assert isinstance(bundle["pages"], list)
        assert catalog["filaments"] == []
        assert timeout_s == 20
        return SimpleNamespace(model_dump=lambda mode: {"title": "Review", "draft": {}})

    monkeypatch.setattr(catalog_intake, "collect_catalog_snapshot", snapshot)
    monkeypatch.setattr(catalog_intake, "read_source_site", reader)
    monkeypatch.setattr(catalog_intake, "parse_reasoner_command", lambda value: [value])
    monkeypatch.setattr(catalog_intake, "build_batched_proposal", batched_proposal)

    args = catalog_intake._parser().parse_args(
        [
            "--source-url",
            "https://maker.example/catalog",
            "--brand-name",
            "Maker",
            "--reasoner-command",
            "reasoner {schema} {output}",
            "--timeout-seconds",
            "20",
        ]
    )
    result = await catalog_intake.build_proposal(args)

    assert result == {"title": "Review", "draft": {}}
    assert calls == ["snapshot", "source", "batched_proposal"]


@pytest.mark.parametrize(
    "origin",
    ["http://catalog.example", "http://127.0.0.1.evil.example", "https://user:secret@example.com"],
)
def test_api_origin_rejects_unsafe_token_destination(origin: str) -> None:
    with pytest.raises(ValueError):
        catalog_intake._api_origin(origin)


@pytest.mark.asyncio
async def test_explicit_api_origin_must_match_configured_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FH_CATALOG_API_ORIGIN", "http://127.0.0.1:8001")
    args = catalog_intake._parser().parse_args([
        "--source-url", "https://maker.example/catalog", "--brand-name", "Maker",
        "--reasoner-command", "reasoner", "--api-origin", "https://other.example", "--submit",
    ])
    with pytest.raises(ValueError, match="must match FH_CATALOG_API_ORIGIN"):
        await catalog_intake.build_proposal(args)


@pytest.mark.asyncio
async def test_submission_uses_only_the_curation_service_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"id": 12, "revision": 1}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, path, **kwargs):
            calls.append((path, kwargs))
            return FakeResponse()

    async def snapshot(client, name, brand_id):
        return {"filaments": [], "selected_brand": None}

    async def reader(urls, *, max_pages):
        return SimpleNamespace(model_dump=lambda: {"pages": [{"url": urls[0], "text": "PLA"}]})

    monkeypatch.setattr(catalog_intake.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(catalog_intake, "collect_catalog_snapshot", snapshot)
    monkeypatch.setattr(catalog_intake, "read_source_site", reader)
    monkeypatch.setattr(catalog_intake, "parse_reasoner_command", lambda _: ["reasoner"])
    monkeypatch.setattr(
        catalog_intake,
        "build_batched_proposal",
        lambda *args, **kwargs: SimpleNamespace(model_dump=lambda mode: {"title": "Review"}),
    )
    monkeypatch.setenv("FH_CATALOG_ADMIN_TOKEN", "must-not-be-used")
    monkeypatch.setenv("FH_CATALOG_SERVICE_TOKEN", "fhca_test-key")
    args = catalog_intake._parser().parse_args([
        "--source-url", "https://maker.example/catalog", "--brand-name", "Maker",
        "--reasoner-command", "reasoner", "--submit",
    ])

    result = await catalog_intake.build_proposal(args)

    assert result == {"proposal_id": 12, "revision": 1}
    assert calls == [(
        "/api/v1/service/catalog/curation/proposals",
        {"json": {"title": "Review"}, "headers": {"Authorization": "Bearer fhca_test-key"}},
    )]
