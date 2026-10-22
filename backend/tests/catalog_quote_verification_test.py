"""Server-side quote verification: matching, verdicts, queue and the apply gate."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import CatalogCurationProposal
from app.models.catalog_quote_check import (
    CatalogImageConfirmation,
    CatalogQuoteCheck,
    CatalogQuoteCheckJob,
)
from app.schemas.catalog_curation import CatalogCurationCreate
from app.schemas.catalog_raw_fact import CatalogRawFact
from app.services import catalog_quote_queue as queue
from app.services.catalog_quote_claims import extract_claims, is_official_host
from app.services.catalog_quote_matching import (
    contains_text,
    leading_quote,
    normalize_text,
    number_present,
    numbers_present,
    squash,
)
from app.services.catalog_quote_verifier import (
    PageText,
    QuoteVerifier,
    decide,
    is_transient_reason,
)
from app.services.catalog_source_reader import (
    CatalogSourceReader,
    SinglePageResult,
    SourceImage,
    SourcePage,
)

pytestmark = pytest.mark.asyncio
BASE = "/api/v1/admin/catalog/curation/proposals"
ACCOUNTS = "/api/v1/admin/catalog/curation/service-accounts"
SERVICE = "/api/v1/service/catalog/curation/proposals"
PAGE = "https://www.maker.example/products/pla"
SPEC = "https://maker.example/tds/pla"
QUOTES = {
    "name": "PLA Black filament for desktop printers",
    "material_type": "Material: PLA (polylactic acid)",
    "diameter": "Filament diameter 1,75 mm",
}


def headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


class Page:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeReader:
    """Stands in for CatalogSourceReader: serves canned pages, counts reads."""

    def __init__(self, pages: dict[str, str], log: list[str], on_read=None, images=None) -> None:
        self.images = images or {}
        self.pages = pages
        self.log = log
        self.on_read = on_read

    async def read_page(self, url: str) -> SinglePageResult:
        self.log.append(url)
        if self.on_read is not None:
            await self.on_read()
        content = self.pages.get(url)
        if content is None:
            return SinglePageResult(None, "http_404")
        if content.startswith("reason:"):
            return SinglePageResult(None, content.removeprefix("reason:"))
        images = tuple(SourceImage(image, "", "") for image in self.images.get(url, ()))
        return SinglePageResult(SourcePage(url, "", (), content, (), (), images), None)


def verifier_for(pages: dict[str, str], log: list[str] | None = None, on_read=None, images=None):
    log = log if log is not None else []
    return QuoteVerifier(reader_factory=lambda: FakeReader(pages, log, on_read, images))


def payload(quotes: dict[str, str | None] | None = None, website="https://maker.example"):
    quotes = QUOTES if quotes is None else quotes
    draft = {
        "filename": "maker.json",
        "brands": [{"brand_key": "maker", "mode": "create", "name": "Maker", "website": website}],
        "filaments": [
            {
                "filament_key": "maker:pla:black",
                "brand_key": "maker",
                "mode": "create",
                "name": "PLA Black",
                "material_type": "PLA",
                "diameter": 1.75,
                "availability": "available",
            }
        ],
    }
    evidence = []
    for sheet, key, row in (
        ("Brands", "maker", draft["brands"][0]),
        ("Filaments", "maker:pla:black", draft["filaments"][0]),
    ):
        for field in ("name", "website", "material_type", "diameter", "availability"):
            if field not in row:
                continue
            item = {
                "sheet": sheet,
                "key": key,
                "field": field,
                "kind": "direct",
                "source_urls": [PAGE],
            }
            if sheet == "Filaments" and quotes.get(field):
                item["quote"] = quotes[field]
            elif sheet == "Filaments" and field == "availability":
                item["kind"] = "inferred"
                item["explanation"] = "Listed as in stock."
            evidence.append(item)
    return {
        "title": "Maker materials",
        "draft": draft,
        "evidence": evidence,
        "unmapped_facts": [],
        "source_facts": [
            {
                "filament_key": "maker:pla:black",
                "property_name": field,
                "value_summary": f"Manufacturer specifies {field}",
                "source_urls": [PAGE],
                "disposition": "mapped",
                "mapped_fields": [field],
            }
            for field in ("name", "material_type", "diameter", "availability")
        ],
        "coverage_note": "Black PLA page reviewed.",
    }


class SharedSession:
    """A session factory over the test's single in-memory database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self) -> AsyncSession:
        return self.db

    async def __aexit__(self, *exc) -> None:
        return None


async def create(client: AsyncClient, admin, body) -> int:
    response = await client.post(BASE, json=body, headers=headers(admin))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def report(client: AsyncClient, admin, proposal_id: int) -> dict:
    response = await client.get(f"{BASE}/{proposal_id}/quote-checks", headers=headers(admin))
    assert response.status_code == 200, response.text
    return response.json()


def statuses(body: dict) -> dict[str, str]:
    return {item["field"]: item["status"] for item in body["items"] if item["sheet"] == "Filaments"}


# --- matching -------------------------------------------------------------


async def test_normalization_folds_typography_case_and_spaces():
    page = normalize_text("Diameter: 1,75 mm  —  “PLA”\n+ filler")
    assert contains_text(page, squash(page), 'DIAMETER: 1,75 mm - "pla" + filler')
    assert contains_text(page, squash(page), "diameter:1,75mm")
    assert not contains_text(page, squash(page), "Filament diameter 2,85 mm")


async def test_a_quote_never_matches_inside_a_longer_number():
    def found(fragment: str, text: str) -> bool:
        page = normalize_text(text)
        return contains_text(page, squash(page), fragment)

    assert not found("75 \u00b0C", "Nozzle 175 \u00b0C")
    assert not found("1.75", "Size 11.75 mm")
    assert not found("75 \u00b0C", "up to 1.75 \u00b0C")
    assert not found("58 \u00b0C", "HDT 58.5 \u00b0C")
    assert found("58 \u00b0C", "HDT: 58 \u00b0C.")
    assert found("1.75", "Size 1,75 mm")


async def test_thousands_separators_are_not_decimals_but_a_lone_group_reads_both_ways():
    assert numbers_present("2300 kg", "weighs 2,300 kg")
    assert not numbers_present("2.3 kg", "weighs 2,3000 kg")
    assert numbers_present("1000 kg", "1,000 kg") and numbers_present("1 kg", "1,000 kg")
    assert not numbers_present("2300", "2.3")


async def test_numbers_match_across_decimal_separators_but_only_as_whole_numbers():
    assert number_present(1.75, "Filament diameter 1,75 mm")
    assert number_present(200.0, "Nozzle 200 °C")
    assert not number_present(75, "Density 175 kg")
    assert not number_present(75, "Version 1.75")
    assert numbers_present("HDT 58 °C at 0.45 MPa", "HDT: 58 C, 0,45 MPa")
    assert not numbers_present("HDT 58 °C", "HDT: 85 C")
    assert numbers_present("Resistant to weak acids", "no digits here")


async def test_legacy_quote_is_recovered_from_the_start_of_explanation():
    assert leading_quote('"PLA, 1.75 mm" shown on the product page') == "PLA, 1.75 mm"
    assert leading_quote("“direct” note") == "direct"
    assert leading_quote("Inferred from the catalog") is None


async def test_unavailable_reasons_split_transient_from_permanent():
    assert is_transient_reason("http_503") and is_transient_reason("timeout")
    assert is_transient_reason("robots_unavailable") and is_transient_reason("http_429")
    assert not is_transient_reason("non_page_resource")  # a TDS PDF
    assert not is_transient_reason("robots_disallowed")
    assert not is_transient_reason("http_404")


def claims_for(body, domains=("maker.example",)):
    return {
        claim.field: claim
        for claim in extract_claims(
            draft=body["draft"],
            evidence=body["evidence"],
            unmapped_facts=[],
            source_facts=[],
            domains=domains,
        )
        if claim.sheet == "Filaments"
    }


async def test_domain_decides_before_any_fetch():
    claims = claims_for(payload())
    log: list[str] = []
    verdicts = await verifier_for({PAGE: QUOTES["name"]}, log).verify(
        list(claims_for(payload(), domains=("other.example",)).values())
    )
    assert {v.status for v in verdicts.values()} == {"not_official_domain"}
    assert log == []
    # www. and subdomains of the brand website are official.
    assert (
        decide(claims["name"], {PAGE: _page("PLA Black filament for desktop printers")}).status
        == "verified"
    )
    assert is_official_host("https://docs.maker.example/x", ["maker.example"])
    assert not is_official_host("https://maker.example.shop.test/x", ["maker.example"])
    assert not is_official_host("https://notmaker.example/x", ["maker.example"])


def _page(text: str):
    normalized = normalize_text(text)
    return PageText(normalized, squash(normalized), "h")


async def test_quote_found_but_value_absent_is_not_verified():
    body = payload({**QUOTES, "diameter": "Filament diameter 2,85 mm"})
    verdicts = await verifier_for(
        {
            PAGE: "Filament diameter 2,85 mm. PLA Black filament for desktop printers. Material: PLA (polylactic acid)"
        }
    ).verify(list(claims_for(body).values()))
    assert verdicts[("evidence", "Filaments", "maker:pla:black", "diameter")].status == (
        "value_not_in_quote"
    )


# --- verdicts -------------------------------------------------------------


async def test_verdicts_cover_every_status_and_fetch_each_page_once():
    body = payload(
        {
            **QUOTES,
            "name": "A sentence the page never says",
            "material_type": "Material: PLA (polylactic acid)",
            "diameter": "Filament diameter 1,75 mm",
        }
    )
    body["evidence"].append(
        {
            "sheet": "Filaments",
            "key": "maker:pla:black",
            "field": "color_name",
            "kind": "direct",
            "source_urls": [PAGE],
            "quote": "Colour: Black, matte finish",
            "image_url": "https://maker.example/specs.png",
        }
    )
    body["draft"]["filaments"][0]["color_name"] = "Black"
    log: list[str] = []
    claims = list(claims_for(body).values())
    verdicts = await verifier_for(
        {PAGE: "Material: PLA (polylactic acid). Filament diameter 1.75 mm"}, log
    ).verify(claims)
    got = {identity[3]: verdict.status for identity, verdict in verdicts.items()}
    assert got["name"] == "quote_not_found"
    assert got["material_type"] == "verified"
    assert got["diameter"] == "verified"
    # an invented quote is not rescued by an image the page does not show
    assert got["color_name"] == "quote_not_found"
    assert log == [PAGE]

    unavailable = await verifier_for({PAGE: "reason:http_503"}).verify(claims)
    assert {v.status for v in unavailable.values()} == {"source_unavailable"}
    assert {v.reason for v in unavailable.values()} == {"http_503"}


async def test_a_run_stops_starting_reads_after_its_budget_and_the_rest_is_retryable():
    log: list[str] = []
    verifier = QuoteVerifier(
        reader_factory=lambda: FakeReader({PAGE: "PLA Black filament for desktop printers"}, log),
        run_budget=-1.0,
    )
    verdicts = await verifier.verify(list(claims_for(payload()).values()))
    assert log == []
    assert {v.status for v in verdicts.values()} == {"source_unavailable"}
    assert is_transient_reason({v.reason for v in verdicts.values()}.pop())


async def test_www_and_bare_host_share_one_request_gate():
    verifier = verifier_for({})
    await verifier._read("https://www.maker.example/a", float("inf"))
    await verifier._read("https://maker.example/b", float("inf"))
    assert list(verifier._hosts) == ["maker.example"]


SPECS = "https://maker.example/img/specs.png"


def image_claim(image_url: str, quote: str | None = None):
    body = payload()
    item = {
        "sheet": "Filaments",
        "key": "maker:pla:black",
        "field": "color_name",
        "kind": "direct",
        "source_urls": [PAGE],
        "image_url": image_url,
    }
    if quote:
        item["quote"] = quote
    body["evidence"].append(item)
    body["draft"]["filaments"][0]["color_name"] = "Black"
    return claims_for(body)["color_name"]


async def test_an_image_counts_only_when_the_cited_page_shows_it_on_an_official_host():
    log: list[str] = []
    shown = {PAGE: "Specifications page"}
    ok = image_claim(SPECS)
    verdicts = await verifier_for(shown, log, images={PAGE: [SPECS]}).verify([ok])
    assert verdicts[ok.identity].status == "image_only"
    assert log == [PAGE]  # an image-only claim is fetched and checked like any other

    absent = image_claim("https://maker.example/img/other.png")
    verdicts = await verifier_for(shown, images={PAGE: [SPECS]}).verify([absent])
    assert verdicts[absent.identity].status == "quote_not_found"

    foreign = image_claim("https://cdn.other.test/specs.png")
    verdicts = await verifier_for(
        shown, images={PAGE: ["https://cdn.other.test/specs.png"]}
    ).verify([foreign])
    assert verdicts[foreign.identity].status == "not_official_domain"

    invented = image_claim("https://maker.example/img/other.png", "Colour: Black, matte finish")
    verdicts = await verifier_for(shown, images={PAGE: [SPECS]}).verify([invented])
    assert verdicts[invented.identity].status == "quote_not_found"


async def test_a_quote_shorter_than_twenty_characters_is_not_checked():
    body = payload({**QUOTES, "diameter": "1,75 mm"})
    log: list[str] = []
    claim = claims_for(body)["diameter"]
    verdicts = await verifier_for({PAGE: "Filament diameter 1,75 mm"}, log).verify([claim])
    assert verdicts[claim.identity].status == "quote_too_short"
    assert log == []


async def test_digit_free_summaries_need_their_words_in_the_quote():
    from app.services.catalog_quote_verifier import _value_matches

    def fact(summary: str, quote: str):
        return extract_claims(
            draft={},
            evidence=[],
            unmapped_facts=[],
            source_facts=[
                {
                    "filament_key": "k",
                    "property_name": "p",
                    "value_summary": summary,
                    "source_urls": [PAGE],
                    "disposition": "unresolved",
                    "quote": quote,
                }
            ],
            domains=("maker.example",),
        )[0]

    assert _value_matches(fact("Resistant to weak acids", "Resistant to weak acids and bases"))
    assert not _value_matches(fact("Resistant to weak acids", "Printed on a rainy Tuesday"))
    assert not _value_matches(fact("HDT 58 C", "Printed on a rainy Tuesday"))


async def test_verdicts_are_cached_between_runs_except_failed_reads():
    claims = list(claims_for(payload()).values())
    log: list[str] = []
    verifier = verifier_for(
        {
            PAGE: "PLA Black filament for desktop printers Material: PLA (polylactic acid) Filament diameter 1.75 mm"
        },
        log,
    )
    await verifier.verify(claims)
    await verifier.verify(claims)
    assert log.count(PAGE) == 1
    failing_log: list[str] = []
    failing = verifier_for({}, failing_log)
    await failing.verify(claims)
    await failing.verify(claims)
    assert failing_log.count(PAGE) == 2


async def test_reader_single_page_reports_why_a_page_was_refused():
    async def public(host: str, port: int) -> set[str]:
        return {"93.184.216.34"}

    def reader(handler) -> CatalogSourceReader:
        return CatalogSourceReader(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            resolver=public,
            default_delay=0,
        )

    seen: list[str] = []

    async def serving(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="<p>Filament diameter 1,75 mm</p>"
        )

    source = reader(serving)
    ok = await source.read_page("https://maker.example/item")
    assert ok.page is not None and "1,75" in ok.page.text
    assert (await source.read_page("https://maker.example/private")).reason == "robots_disallowed"
    assert (await source.read_page("https://maker.example/missing")).reason == "http_404"
    assert (await source.read_page("https://maker.example/file.zip")).reason == "non_page_resource"
    assert (await source.read_page("http://127.0.0.1/x")).reason == "unsafe_url"
    assert seen.count("/robots.txt") == 1  # fetched once per origin, then cached

    clock = [0.0]
    robots_up = [False]

    async def recovering(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            if robots_up[0]:
                return httpx.Response(200, text="User-agent: *\nAllow: /")
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>fine</p>")

    flaky = reader(recovering)
    flaky._robots_clock = lambda: clock[0]
    assert (await flaky.read_page("https://maker.example/item")).reason == "robots_unavailable"
    robots_up[0] = True
    assert (await flaky.read_page("https://maker.example/item")).reason == "robots_unavailable"
    clock[0] = 500.0  # past the short error TTL: the host is not blocked for good
    assert (await flaky.read_page("https://maker.example/item")).page is not None

    async def aliased(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.maker.example":
            return httpx.Response(
                301, headers={"location": f"https://maker.example{request.url.path}"}
            )
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>moved</p>")

    strict = reader(aliased)
    assert (await strict.read_page("https://www.maker.example/item")).page is None
    tolerant = CatalogSourceReader(
        client=httpx.AsyncClient(transport=httpx.MockTransport(aliased)),
        resolver=public,
        default_delay=0,
        www_alias=True,
    )
    assert (await tolerant.read_page("https://www.maker.example/item")).page is not None

    async def broken_robots(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503 if request.url.path == "/robots.txt" else 200, text="<p>x</p>")

    assert (await reader(broken_robots).read_page("https://maker.example/item")).reason == (
        "robots_unavailable"
    )


# --- raw fact format and contract compatibility ---------------------------


async def test_raw_fact_example_file_is_valid_and_the_format_is_strict():
    path = Path(__file__).parent / "fixtures" / "catalog_raw_facts_example.jsonl"
    facts = [
        CatalogRawFact.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [fact.subject for fact in facts][:2] == ["brand", "line:PLA Pro"]
    assert facts[2].image_url is not None and facts[2].unit == "g/cm³"
    base = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    for change in (
        {"subject": "family:PLA"},
        {"subject": "line:"},
        {"quote": "   "},
        {"quote": "x" * 501},
        {"page_url": "https://user:secret@maker.example/x"},
        {"page_url": "ftp://maker.example/x"},
        {"collected_at": "2026-10-21T09:00:00"},
        {"invented": 1},
    ):
        with pytest.raises(ValidationError):
            CatalogRawFact.model_validate({**base, **change})
    open_format = CatalogRawFact.model_validate(
        {
            **base,
            "property_source_name": "Unheard-of property",
            "material_type_source_name": "PA12-CF",
        }
    )
    assert open_format.material_type_source_name == "PA12-CF"


async def test_proposal_stored_before_the_new_fields_still_loads_previews_and_reports(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    old = payload()
    for item in old["evidence"]:
        item.pop("quote", None)
    CatalogCurationCreate.model_validate(old)  # old payload shape is still the contract
    row = CatalogCurationProposal(
        title=old["title"],
        draft=old["draft"],
        evidence=old["evidence"],
        unmapped_facts=[
            {
                "filament_key": "maker:pla:black",
                "property_name": "Acids",
                "value_summary": "Weak acids",
                "source_urls": [PAGE],
            }
        ],
        source_facts=old["source_facts"],
        coverage_note=old["coverage_note"],
        created_by_user_id=admin_user.id,
    )
    db_session.add(row)
    await db_session.commit()
    loaded = await client.get(f"{BASE}/{row.id}", headers=headers(admin_user))
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["evidence"][0].get("quote") is None
    preview = await client.post(
        f"{BASE}/{row.id}/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] == 0, preview.json()["rows"]
    assert (await report(client, admin_user, row.id))["summary"]["total"] == 0
    refused = await client.post(f"{BASE}/{row.id}/verify-sources", headers=headers(admin_user))
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "ERR_CATALOG_CURATION_NO_QUOTES"


# --- API, queue and the apply gate ----------------------------------------


async def test_verify_sources_is_admin_only_and_idempotent(
    client: AsyncClient, db_session: AsyncSession, admin_user, auth_user
):
    proposal_id = await create(client, admin_user, payload())
    url = f"{BASE}/{proposal_id}/verify-sources"
    assert (await client.post(url)).status_code == 401
    assert (await client.post(url, headers=headers(auth_user))).status_code == 403
    assert (
        await client.get(f"{BASE}/{proposal_id}/quote-checks", headers=headers(auth_user))
    ).status_code == 403
    first = await client.post(url, headers=headers(admin_user))
    again = await client.post(url, headers=headers(admin_user))
    assert first.status_code == again.status_code == 202
    assert first.json()["job_pending"] is True
    assert first.json()["summary"]["pending"] == first.json()["summary"]["total"] == 3
    assert await db_session.scalar(select(func.count()).select_from(CatalogQuoteCheckJob)) == 1
    assert (
        await client.post(f"{BASE}/999/verify-sources", headers=headers(admin_user))
    ).status_code == 404


async def test_service_account_writes_enqueue_a_check_only_when_quotes_are_cited(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    created = await client.post(ACCOUNTS, json={"name": "agent"}, headers=headers(admin_user))
    token = {"Authorization": f"Bearer {created.json()['token']}"}
    plain = payload({})
    plain["evidence"] = [{k: v for k, v in e.items() if k != "quote"} for e in plain["evidence"]]
    first = await client.post(SERVICE, json=plain, headers=token)
    assert first.status_code == 201, first.text
    assert await db_session.scalar(select(func.count()).select_from(CatalogQuoteCheckJob)) == 0
    quoted = await client.post(SERVICE, json=payload(), headers=token)
    assert quoted.status_code == 201, quoted.text
    jobs = (await db_session.scalars(select(CatalogQuoteCheckJob))).all()
    assert [job.proposal_id for job in jobs] == [quoted.json()["id"]]
    edit = await client.patch(
        f"{SERVICE}/{first.json()['id']}",
        json={"revision": 1, "evidence": payload()["evidence"]},
        headers=token,
    )
    assert edit.status_code == 200, edit.text
    assert await db_session.scalar(select(func.count()).select_from(CatalogQuoteCheckJob)) == 2


async def test_worker_verifies_once_and_unverified_quotes_block_applying(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    proposal_id = await create(client, admin_user, payload())
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))

    def preview():
        return client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 1}, headers=headers(admin_user)
        )

    before = (await preview()).json()
    blocked = [row for row in before["rows"] if row["status"] == "error"]
    assert blocked and "Source quote not verified" in blocked[0]["message"]
    assert before["confirmation_token"] is None

    log: list[str] = []
    verifier = verifier_for(
        {
            PAGE: "PLA Black filament for desktop printers. Material: PLA (polylactic acid). Filament diameter 1,75 mm."
        },
        log,
    )
    factory = SharedSession(db_session)
    assert await queue.process_quote_check_jobs(factory, verifier) == 1
    assert await queue.process_quote_check_jobs(factory, verifier) == 0  # job is gone: not rerun
    assert log == [PAGE]
    after = await report(client, admin_user, proposal_id)
    assert after["job_pending"] is False
    assert after["summary"]["verified"] == 3 and after["summary"]["verified_percent"] == 100
    ok = (await preview()).json()
    assert ok["summary"]["error"] == 0, ok["rows"]
    assert ok["confirmation_token"]


async def test_a_source_fact_with_an_unverified_quote_is_named_in_the_blocked_row(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    body = payload()
    body["source_facts"][0]["quote"] = "A sentence the page never says"
    proposal_id = await create(client, admin_user, body)
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    page = "PLA Black filament for desktop printers. Material: PLA (polylactic acid). Filament diameter 1,75 mm."
    await queue.process_quote_check_jobs(SharedSession(db_session), verifier_for({PAGE: page}))
    preview = (
        await client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 1}, headers=headers(admin_user)
        )
    ).json()
    message = next(row["message"] for row in preview["rows"] if row["status"] == "error")
    assert "Source quote not verified for: name (quote_not_found)" in message
    assert "unresolved 1" in message
    review = next(
        r for r in preview["source_facts_review"] if r["filament_key"] == "maker:pla:black"
    )
    assert review["unresolved"] == 1 and review["mapped"] == 3


async def test_not_found_quote_blocks_and_an_edited_quote_returns_to_pending(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    body = payload({**QUOTES, "name": "PLA Black filament for desktop printers"})
    proposal_id = await create(client, admin_user, body)
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    verifier = verifier_for({PAGE: "Material: PLA (polylactic acid). Filament diameter 1,75 mm."})
    await queue.process_quote_check_jobs(SharedSession(db_session), verifier)
    assert statuses(await report(client, admin_user, proposal_id))["name"] == "quote_not_found"
    preview = (
        await client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 1}, headers=headers(admin_user)
        )
    ).json()
    assert preview["confirmation_token"] is None

    fixed = deepcopy(body["evidence"])
    for item in fixed:
        if item["field"] == "name" and item["sheet"] == "Filaments":
            item["quote"] = "Material: PLA (polylactic acid)"
    edited = await client.patch(
        f"{BASE}/{proposal_id}",
        json={"revision": 1, "evidence": fixed},
        headers=headers(admin_user),
    )
    assert edited.status_code == 200, edited.text
    assert statuses(await report(client, admin_user, proposal_id))["name"] == "pending"


async def test_unavailable_source_is_retried_with_backoff_then_given_up(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    proposal_id = await create(client, admin_user, payload())
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    log: list[str] = []
    verifier = verifier_for({PAGE: "reason:http_503"}, log)
    factory = SharedSession(db_session)
    for attempt in range(1, queue.MAX_ATTEMPTS):
        assert await queue.process_quote_check_jobs(factory, verifier) == 1
        job = await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True)
        assert job.attempt_count == attempt and job.claimed_at is None
        assert job.next_attempt_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert await queue.process_quote_check_jobs(factory, verifier) == 0  # backing off
        job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()
    assert await queue.process_quote_check_jobs(factory, verifier) == 1
    assert await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True) is None
    assert len(log) == queue.MAX_ATTEMPTS
    assert set(statuses(await report(client, admin_user, proposal_id)).values()) == {
        "source_unavailable"
    }


async def test_permanent_refusal_is_not_retried(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    body = payload()
    proposal_id = await create(client, admin_user, body)
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    verifier = verifier_for({PAGE: "reason:non_page_resource"})
    assert await queue.process_quote_check_jobs(SharedSession(db_session), verifier) == 1
    assert await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True) is None
    row = await db_session.scalar(select(CatalogQuoteCheck).limit(1))
    assert row.status == "source_unavailable" and row.reason == "non_page_resource"


async def test_job_is_leased_while_running_and_a_mid_run_request_is_not_lost(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    proposal_id = await create(client, admin_user, payload())
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    factory = SharedSession(db_session)
    claimed = await queue._claim_job(factory)
    assert claimed is not None and claimed[0] == proposal_id
    assert await queue._claim_job(factory) is None  # leased: a second worker skips it
    job = await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True)
    job.claimed_at = None
    await db_session.commit()

    requested = False

    async def request_again() -> None:
        nonlocal requested
        if not requested:
            requested = True
            await queue.enqueue_quote_check(db_session, proposal_id)
            await db_session.commit()

    verifier = verifier_for(
        {
            PAGE: "PLA Black filament for desktop printers Material: PLA (polylactic acid) Filament diameter 1,75 mm"
        },
        on_read=request_again,
    )
    assert await queue.process_quote_check_jobs(factory, verifier) == 1
    survivor = await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True)
    assert survivor is not None and survivor.claimed_at is None
    assert await queue.process_quote_check_jobs(factory, verifier) == 1
    assert await db_session.get(CatalogQuoteCheckJob, proposal_id, populate_existing=True) is None


async def test_legacy_explanation_quote_is_checked_but_never_blocks(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    body = payload({})
    for item in body["evidence"]:
        if item["sheet"] == "Filaments" and item["field"] == "diameter":
            item["explanation"] = '"Filament diameter 1,75 mm" on the page'
    body["draft"]["filaments"][0]["diameter"] = 2.85
    proposal_id = await create(client, admin_user, body)
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    await queue.process_quote_check_jobs(
        SharedSession(db_session), verifier_for({PAGE: "Filament diameter 1,75 mm"})
    )
    result = await report(client, admin_user, proposal_id)
    legacy = [item for item in result["items"] if item["field"] == "diameter"]
    assert legacy[0]["status"] == "value_not_in_quote" and legacy[0]["gating"] is False
    preview = (
        await client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 1}, headers=headers(admin_user)
        )
    ).json()
    assert preview["summary"]["error"] == 0, preview["rows"]


async def test_an_image_claim_passes_only_after_an_admin_confirms_it_and_an_edit_withdraws_it(
    client: AsyncClient, db_session: AsyncSession, admin_user, auth_user
):
    body = payload({})
    for item in body["evidence"]:
        if item["sheet"] == "Filaments" and item["field"] == "diameter":
            item["image_url"] = SPECS
    proposal_id = await create(client, admin_user, body)
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    verifier = verifier_for({PAGE: "Specifications"}, images={PAGE: [SPECS]})
    await queue.process_quote_check_jobs(SharedSession(db_session), verifier)
    first = await report(client, admin_user, proposal_id)
    assert first["summary"]["image_only"] == 1 and first["items"][0]["confirmed"] is False

    def preview():
        return client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 1}, headers=headers(admin_user)
        )

    blocked = (await preview()).json()
    assert blocked["confirmation_token"] is None
    assert "diameter (image_unconfirmed)" in next(
        row["message"] for row in blocked["rows"] if row["status"] == "error"
    )

    url = f"{BASE}/{proposal_id}/quote-checks/image-confirmation"
    claim = {
        "scope": "evidence",
        "sheet": "Filaments",
        "key": "maker:pla:black",
        "field": "diameter",
    }
    assert (await client.post(url, json={**claim, "confirmed": True})).status_code == 401
    forbidden = await client.post(
        url, json={**claim, "confirmed": True}, headers=headers(auth_user)
    )
    assert forbidden.status_code == 403
    unknown = await client.post(
        url, json={**claim, "field": "density", "confirmed": True}, headers=headers(admin_user)
    )
    assert unknown.status_code == 422

    done = await client.post(url, json={**claim, "confirmed": True}, headers=headers(admin_user))
    assert done.status_code == 200, done.text
    assert done.json()["items"][0]["confirmed"] is True
    row = await db_session.scalar(select(CatalogImageConfirmation))
    assert row.confirmed_by_user_id == admin_user.id and row.confirmed_at is not None
    again = await client.post(url, json={**claim, "confirmed": True}, headers=headers(admin_user))
    assert again.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(CatalogImageConfirmation)) == 1
    passed = (await preview()).json()
    assert passed["summary"]["error"] == 0 and passed["confirmation_token"]

    edited = deepcopy(body["evidence"])
    for item in edited:
        if item["sheet"] == "Filaments" and item["field"] == "diameter":
            item["image_url"] = "https://maker.example/img/other.png"
    patched = await client.patch(
        f"{BASE}/{proposal_id}",
        json={"revision": 1, "evidence": edited},
        headers=headers(admin_user),
    )
    assert patched.status_code == 200, patched.text
    after = await report(client, admin_user, proposal_id)
    assert after["items"][0]["status"] == "pending" and after["items"][0]["confirmed"] is False
    assert (
        await client.post(
            f"{BASE}/{proposal_id}/preview", json={"revision": 2}, headers=headers(admin_user)
        )
    ).json()["confirmation_token"] is None

    withdrawn = await client.post(
        url, json={**claim, "confirmed": False}, headers=headers(admin_user)
    )
    assert withdrawn.status_code == 422  # no longer an image_only claim of this revision


async def test_the_report_lists_only_claims_that_are_not_verified(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    proposal_id = await create(client, admin_user, payload())
    await client.post(f"{BASE}/{proposal_id}/verify-sources", headers=headers(admin_user))
    page = "PLA Black filament for desktop printers. Filament diameter 1,75 mm."
    await queue.process_quote_check_jobs(SharedSession(db_session), verifier_for({PAGE: page}))
    result = await report(client, admin_user, proposal_id)
    assert result["summary"]["total"] == 3 and result["summary"]["verified"] == 2
    assert [item["field"] for item in result["items"]] == ["material_type"]


# --- PDF datasheets -------------------------------------------------------

PDF_URL = "https://maker.example/tds/pla.pdf"


def make_pdf(text: str | None) -> bytes:
    """A one-page PDF built by hand; ``None`` gives a page with no text at all (a scan)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else ""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        " /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    ).encode()
    return out


def encrypted(pdf: bytes) -> bytes:
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.encrypt("owner-secret", algorithm="AES-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def pdf_verifier(body: bytes) -> QuoteVerifier:
    async def public(host: str, port: int) -> set[str]:
        return {"93.184.216.34"}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return QuoteVerifier(
        reader_factory=lambda: CatalogSourceReader(client=client, resolver=public, default_delay=0)
    )


def pdf_claim(quote: str):
    body = payload({**QUOTES, "diameter": quote})
    for item in body["evidence"]:
        item["source_urls"] = [PDF_URL]
    return claims_for(body)["diameter"]


async def check_pdf(body: bytes, quote: str = "Filament diameter 1,75 mm"):
    claim = pdf_claim(quote)
    verdicts = await pdf_verifier(body).verify([claim])
    return verdicts[claim.identity]


async def test_a_quote_is_verified_against_the_text_of_a_pdf_datasheet():
    good = await check_pdf(make_pdf("Filament diameter 1.75 mm +- 0.05"))
    assert good.status == "verified" and good.page_sha256
    other = await check_pdf(make_pdf("Printing temperature 215 C and bed 60 C"))
    assert other.status == "quote_not_found"
    wrong_value = await check_pdf(
        make_pdf("Filament diameter 2.85 mm"), "Filament diameter 2,85 mm"
    )
    assert wrong_value.status == "value_not_in_quote"  # the draft says 1.75


async def test_unreadable_pdfs_never_pass_and_never_raise(monkeypatch):
    from app.services import catalog_source_reader

    broken = await check_pdf(b"%PDF-1.4\nthis is not a pdf at all")
    assert (broken.status, broken.reason) == ("source_unavailable", "pdf_unreadable")
    locked = await check_pdf(encrypted(make_pdf("Filament diameter 1.75 mm +- 0.05")))
    assert (locked.status, locked.reason) == ("source_unavailable", "pdf_encrypted")
    scan = await check_pdf(make_pdf(None))
    assert (scan.status, scan.reason) == ("source_unavailable", "pdf_no_text")
    for verdict in (broken, locked, scan):
        assert not is_transient_reason(verdict.reason)  # retrying cannot help

    monkeypatch.setattr(catalog_source_reader, "MAX_PDF_BYTES", 500)
    big = await check_pdf(make_pdf("Filament diameter 1.75 mm +- 0.05 " + "x" * 600))
    assert (big.status, big.reason) == ("source_unavailable", "body_limit")


async def test_a_crawl_still_refuses_pdfs():
    async def public(host: str, port: int) -> set[str]:
        return {"93.184.216.34"}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=make_pdf("x")
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = CatalogSourceReader(client=client, resolver=public, default_delay=0)
    from app.services.catalog_source_reader import CrawlManifest

    manifest = CrawlManifest()
    body, _, _ = await reader._fetch(client, PDF_URL, PDF_URL, manifest)
    assert body is None and manifest.blocked[-1]["reason"] == "non_page_resource"
