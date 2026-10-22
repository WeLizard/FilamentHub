"""Semantic runner contracts: source layout differences must not become material rows."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

import app.services.catalog_semantic_runner as semantic_runner
from app.services.catalog_semantic_runner import (
    build_batched_proposal,
    build_prompt,
    compile_report,
    run_reasoner,
    semantic_report_schema,
)

PAGE_PRODUCT = "https://maker.example/catalog/pla-silk"
PAGE_BLUE = "https://maker.example/catalog/pla-silk-blue"
PAGE_WHITE = "https://maker.example/catalog/pla-silk-white"
PAGE_FAQ = "https://maker.example/help/printing"


def _runner_temp() -> str:
    return os.environ.get("NEIRI_TEMP_DIR") or tempfile.gettempdir()


class _DirectTempRoot:
    """Use the already-authorized test temp root for subprocess protocol tests."""

    def __init__(self, *, prefix: str, dir: str):
        self.path = Path(dir)
        self.files = [self.path / "schema.json", self.path / "report.json"]
        if any(path.exists() for path in self.files):
            raise RuntimeError("Reasoner test temp root contains stale protocol files")

    def __enter__(self) -> str:
        return str(self.path)

    def __exit__(self, exc_type, exc, traceback) -> None:
        for path in self.files:
            if path.exists():
                path.unlink()


def bundle() -> dict:
    return {
        "manufacturer": {"name": "Maker", "website": "https://maker.example"},
        "pages": [
            {
                "url": PAGE_PRODUCT,
                "title": "PLA Silk",
                "text": "PLA Silk comes in several colors and diameters. Spool and sample formats.",
                "links": [PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
            },
            {
                "url": PAGE_BLUE,
                "title": "Blue PLA Silk 1.75 mm",
                "text": "Blue PLA Silk; recommended nozzle 205-225 C.",
                "links": [PAGE_PRODUCT, PAGE_FAQ],
            },
            {
                "url": PAGE_WHITE,
                "title": "White PLA Silk 1.75 mm",
                "text": "White PLA Silk; this color needs a 220-235 C nozzle range.",
                "links": [PAGE_PRODUCT, PAGE_FAQ],
            },
            {
                "url": PAGE_FAQ,
                "title": "Printing recommendations",
                "text": "For PLA Silk, bed 50-60 C. Blue and white follow the material's shared guidance except where their product pages specify otherwise.",
                "links": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE],
            },
        ],
    }


def catalog() -> dict:
    return {
        "brands": [{"id": 4, "name": "Maker", "slug": "maker"}],
        "filaments": [{"id": 31, "brand_id": 4, "name": "PLA Silk Blue", "material_type": "PLA"}],
    }


def _evidence(sheet: str, key: str, row: dict, urls: list[str]) -> list[dict]:
    return [
        {
            "sheet": sheet,
            "key": key,
            "field": field,
            "kind": "direct",
            "source_urls": [url],
        }
        for field, value in row.items()
        if field not in {"enabled", "mode", "overwrite", "brand_key", "filament_key"}
        and value not in (None, "", [], {})
        for url in [PAGE_FAQ if field.startswith("recommended_bed_temp_") else urls[0]]
    ]


def semantic_report(*, conflict_white: bool = False) -> dict:
    brand = {"brand_key": "maker", "mode": "update", "existing_brand": "4", "name": "Maker"}
    blue = {
        "filament_key": "maker:pla-silk:blue:1.75",
        "brand_key": "maker",
        "mode": "update",
        "existing_filament": "31",
        "name": "PLA Silk Blue",
        "material_type": "PLA",
        "line": "PLA Silk",
        "color_name": "Blue",
        "diameter": 1.75,
        "recommended_nozzle_temp_min": 205,
        "recommended_nozzle_temp_max": 225,
        "recommended_bed_temp_min": 50,
        "recommended_bed_temp_max": 60,
        "availability": "available",
    }
    white = {
        "filament_key": "maker:pla-silk:white:1.75",
        "brand_key": "maker",
        "mode": "create",
        "name": "PLA Silk White",
        "material_type": "PLA",
        "line": "PLA Silk",
        "color_name": "White",
        "diameter": 1.75,
        "recommended_nozzle_temp_min": 220,
        "recommended_nozzle_temp_max": 235,
        "recommended_bed_temp_min": 50,
        "recommended_bed_temp_max": 60,
        "availability": "available",
    }
    rows = {"Brands": [brand], "Filaments": [blue, white]}
    sources = {
        "Brands": {"maker": [PAGE_PRODUCT]},
        "Filaments": {
            blue["filament_key"]: [PAGE_BLUE, PAGE_FAQ],
            white["filament_key"]: [PAGE_WHITE, PAGE_FAQ],
        },
    }
    evidence = [
        item
        for sheet, sheet_rows in rows.items()
        for row in sheet_rows
        for item in _evidence(
            sheet,
            row.get("brand_key") if sheet == "Brands" else row["filament_key"],
            row,
            sources[sheet][row.get("brand_key") if sheet == "Brands" else row["filament_key"]],
        )
    ]
    issue = []
    if conflict_white:
        issue = [
            {
                "sheet": "Filaments",
                "key": white["filament_key"],
                "fields": ["recommended_nozzle_temp_min", "recommended_nozzle_temp_max"],
                "kind": "conflict",
                "source_urls": [PAGE_WHITE, PAGE_FAQ],
                "explanation": "The product page and shared guidance disagree about this variant's nozzle range.",
            }
        ]
    return {
        "schema_version": 1,
        "coverage": {
            "status": "complete",
            "discovered_urls": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
            "reviewed_urls": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
            "gaps": [],
            "excluded_sources": [],
        },
        "identities": [
            {
                "filament_key": blue["filament_key"],
                "source_urls": [PAGE_BLUE, PAGE_FAQ, PAGE_PRODUCT],
                "line": "PLA Silk",
                "composition_summary": "PLA-based silk material",
                "color_summary": "Blue",
                "diameter": 1.75,
                "packaging_alias_urls": [PAGE_PRODUCT],
                "existing_filament_id": 31,
                "match_reason": "Same named material, line, color and diameter as the existing record.",
                "candidate_ids": [31],
                "unresolved": False,
            },
            {
                "filament_key": white["filament_key"],
                "source_urls": [PAGE_WHITE, PAGE_FAQ],
                "line": "PLA Silk",
                "composition_summary": "PLA-based silk material",
                "color_summary": "White",
                "diameter": 1.75,
                "packaging_alias_urls": [],
                "existing_filament_id": None,
                "match_reason": None,
                "candidate_ids": [],
                "unresolved": False,
            },
        ],
        "proposal": {
            "title": "Maker catalog review",
            "draft": {
                "filename": "maker-semantic-review.json",
                "brands": [brand],
                "filaments": [blue, white],
                "brand_markets": [],
                "filament_markets": [],
                "presets": [],
            },
            "evidence": evidence,
            "unmapped_facts": [],
            "source_facts": [],
            "coverage_note": "Material pages and shared printing guidance reviewed.",
        },
        "issues": issue,
    }


def test_semantic_compiler_merges_packaging_and_inherits_group_guidance_with_exception():
    report = compile_report(semantic_report(), bundle(), catalog())

    assert len(report.draft.filaments) == 2
    blue, white = report.draft.filaments
    assert blue["recommended_bed_temp_min"] == white["recommended_bed_temp_min"] == 50
    assert blue["recommended_nozzle_temp_min"] == 205
    assert white["recommended_nozzle_temp_min"] == 220
    assert report.draft.brands[0].get("enabled", True) is True
    assert report.coverage_note.find("Source coverage: complete") >= 0


def test_semantic_compiler_preserves_supported_but_unmapped_manufacturer_facts():
    report_data = semantic_report()
    fact = {
        "filament_key": "maker:pla-silk:white:1.75",
        "property_name": "Chemical resistance",
        "value_summary": "Resistant to weak acids",
        "explanation": "The manufacturer states this on the white variant page.",
        "source_urls": [PAGE_WHITE],
    }
    report_data["proposal"]["unmapped_facts"] = [fact]
    compiled = compile_report(report_data, bundle(), catalog())
    assert [item.model_dump(mode="json", include=set(fact)) for item in compiled.unmapped_facts] == [fact]

    report_data["proposal"]["unmapped_facts"][0]["source_urls"] = [
        "https://outside.example/not-fetched"
    ]
    with pytest.raises(ValueError, match="fetched manifest"):
        compile_report(report_data, bundle(), catalog())


def test_semantic_compiler_requires_source_facts_to_link_to_rows_and_supported_evidence():
    report = semantic_report()
    report["proposal"]["source_facts"] = [
        {
            "filament_key": "maker:pla-silk:white:1.75",
            "property_name": "Nozzle range",
            "value_summary": "205–235 C",
            "source_urls": [PAGE_WHITE],
            "disposition": "mapped",
            "mapped_fields": ["recommended_nozzle_temp_min", "recommended_nozzle_temp_max"],
        }
    ]
    compiled = compile_report(report, bundle(), catalog())
    assert compiled.source_facts[0].mapped_fields == [
        "recommended_nozzle_temp_min", "recommended_nozzle_temp_max"
    ]
    report["proposal"]["draft"]["filaments"][1]["recommended_nozzle_temp_min"] = None
    with pytest.raises(ValueError, match="proposed value"):
        compile_report(report, bundle(), catalog())


def test_conflict_disables_only_row_and_its_descendants():
    report_data = semantic_report(conflict_white=True)
    report_data["proposal"]["draft"]["presets"] = [
        {
            "preset_key": "maker:white:generic",
            "filament_key": "maker:pla-silk:white:1.75",
            "enabled": True,
        }
    ]
    report = compile_report(report_data, bundle(), catalog())

    assert report.draft.filaments[0].get("enabled", True) is True
    assert report.draft.filaments[1]["enabled"] is False
    assert report.draft.presets[0]["enabled"] is False
    assert "disagree" in report.coverage_note


def test_missing_or_unsupported_issue_does_not_disable_unrelated_material():
    report_data = semantic_report()
    report_data["issues"] = [
        {
            "sheet": "Filaments",
            "key": "maker:pla-silk:white:1.75",
            "fields": ["drying_temperature_c"],
            "kind": "unsupported",
            "source_urls": [PAGE_WHITE],
            "explanation": "The source gives a range that this field cannot represent.",
        }
    ]
    report = compile_report(report_data, bundle(), catalog())
    assert report.draft.filaments[1].get("enabled", True) is True
    assert "cannot represent" in report.coverage_note


def test_create_without_supported_diameter_stays_editable_but_disabled():
    report_data = semantic_report()
    report_data["proposal"]["draft"]["filaments"][1]["diameter"] = None
    report = compile_report(report_data, bundle(), catalog())

    assert report.draft.filaments[0].get("enabled", True) is True
    assert report.draft.filaments[1]["enabled"] is False
    assert "needs source-supported diameter" in report.coverage_note


def test_semantic_report_cannot_cite_unfetched_external_page():
    report = semantic_report()
    report["proposal"]["evidence"][0]["source_urls"] = ["https://elsewhere.example/claim"]
    with pytest.raises(ValueError, match="fetched manifest"):
        compile_report(report, bundle(), catalog())


def test_prompt_preserves_page_context_and_treats_source_as_untrusted():
    prompt = build_prompt(bundle(), catalog())
    assert "shared guidance" in prompt
    assert PAGE_FAQ in prompt
    assert "untrusted evidence" in prompt
    assert "CATALOG_FIELD_CONTRACT_JSON" in prompt


def test_output_schema_is_closed_and_encodes_flexible_draft_as_json_text():
    schema = semantic_report_schema()
    for definition in [schema, *schema["$defs"].values()]:
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])
    proposal = schema["$defs"]["CatalogCurationCreate"]
    assert proposal["properties"]["draft"]["type"] == "string"
    assert "unmapped_facts" in proposal["properties"]
    assert "CatalogImportDraft" not in schema["$defs"]


def test_reasoner_uses_stdin_and_structured_file_placeholders(monkeypatch):
    temp_root = _runner_temp()
    monkeypatch.setenv("NEIRI_TEMP_DIR", temp_root)
    monkeypatch.setattr(semantic_runner.tempfile, "TemporaryDirectory", _DirectTempRoot)
    report = semantic_report()
    encoded = json.dumps(report)
    existing_temp_dirs = {name for name in os.listdir(temp_root) if name.startswith("fh-semantic-")}
    script = (
        "import pathlib,sys; pathlib.Path(sys.argv[2]).write_text("
        + repr(encoded)
        + ", encoding='utf-8')"
    )
    result = run_reasoner(
        [sys.executable, "-c", script, "{schema}", "{output}"],
        "bounded input",
        semantic_report_schema(),
        timeout_s=10,
    )
    assert result["schema_version"] == 1
    assert existing_temp_dirs == {
        name for name in os.listdir(temp_root) if name.startswith("fh-semantic-")
    }


def test_reasoner_requires_both_placeholders():
    with pytest.raises(ValueError, match="placeholders"):
        run_reasoner([sys.executable, "-c", "pass", "{output}"], "", {}, timeout_s=1)


def test_reasoner_does_not_inherit_application_tokens_or_api_keys(monkeypatch):
    temp_root = _runner_temp()
    monkeypatch.setenv("NEIRI_TEMP_DIR", temp_root)
    monkeypatch.setattr(semantic_runner.tempfile, "TemporaryDirectory", _DirectTempRoot)
    monkeypatch.setenv("FH_CATALOG_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "api-secret")
    runtime_home = str(os.path.join(temp_root, "runtime-config"))
    monkeypatch.setenv("CODEX_HOME", runtime_home)
    script = (
        "import json,os,sys; "
        "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps("
        "{'admin':os.getenv('FH_CATALOG_ADMIN_TOKEN'),"
        "'api':os.getenv('OPENAI_API_KEY'),"
        "'home':os.getenv('CODEX_HOME')}))"
    )
    result = run_reasoner(
        [sys.executable, "-c", script, "{schema}", "{output}"],
        "bounded input",
        {},
        timeout_s=10,
    )
    assert result == {"admin": None, "api": None, "home": runtime_home}


def test_catalog_snapshot_candidate_ids_are_enforced():
    report = semantic_report()
    report["identities"][0]["candidate_ids"] = [999]
    with pytest.raises(ValueError, match="outside the catalog snapshot"):
        compile_report(report, bundle(), catalog())


def test_unreviewed_discovered_allowed_url_marks_partial_coverage():
    source_bundle = deepcopy(bundle())
    source_bundle["allowed_urls"] = ["https://maker.example/catalog/unread"]
    report = semantic_report()
    report["coverage"]["status"] = "partial"
    report["coverage"]["discovered_urls"].append("https://maker.example/catalog/unread")
    report["coverage"]["gaps"] = [
        {"url": "https://maker.example/catalog/unread", "reason": "Could not be fetched"}
    ]
    compiled = compile_report(report, source_bundle, catalog())
    assert "Could not be fetched" in compiled.coverage_note


def test_reader_manifest_blocked_sources_and_partial_flag_survive_compilation():
    source_bundle = deepcopy(bundle())
    blocked = "https://maker.example/catalog/material-limited"
    source_bundle["manifest"] = {
        "partial": True,
        "visited": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
        "discovered": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ, blocked],
        "blocked": [{"url": blocked, "reason": "Access denied by source host"}],
        "archive_candidates": [],
    }
    report = semantic_report()
    report["coverage"]["discovered_urls"].append(blocked)
    compiled = compile_report(report, source_bundle, catalog())

    assert "Source coverage: partial" in compiled.coverage_note
    assert blocked in compiled.coverage_note
    assert "Access denied by source host" in compiled.coverage_note


def test_routine_non_page_resources_do_not_force_partial_coverage():
    source_bundle = deepcopy(bundle())
    source_bundle["pages"][0]["links"] = [
        {"text": "Product page", "url": PAGE_BLUE},
        {"text": "Image", "url": "https://maker.example/media/logo.png"},
        {"text": "Unsafe", "url": "javascript:alert(1)"},
    ]
    source_bundle["manifest"] = {
        "partial": False,
        "visited": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
        "discovered": [PAGE_PRODUCT, PAGE_BLUE, PAGE_WHITE, PAGE_FAQ],
        "blocked": [
            {"url": "javascript:alert(1)", "kind": "unsafe_link"},
            {"url": "https://maker.example/media/logo.png", "kind": "non_page_resource"},
        ],
        "archive_candidates": [],
    }
    compiled = compile_report(semantic_report(), source_bundle, catalog())
    assert "Source coverage: complete" in compiled.coverage_note


def test_large_source_bundle_is_bounded_and_compilation_marks_partial():
    source_bundle = deepcopy(bundle())
    source_bundle["pages"][0]["text"] = "x" * (1500 * 1024)
    prompt = build_prompt(source_bundle, catalog())
    assert len(prompt.encode("utf-8")) < 5 * 1024 * 1024
    assert "runner_input_truncations" in prompt

    compiled = compile_report(semantic_report(), source_bundle, catalog())
    assert "Source coverage: partial" in compiled.coverage_note
    assert PAGE_PRODUCT in compiled.coverage_note


def test_transcribed_image_observation_is_injected_and_can_be_cited_with_its_page():
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/pla-color-chart.png"
    source_bundle["pages"][1]["images"] = [{"url": image_url, "alt": "Color chart"}]
    source_bundle["image_observations"] = {
        "observations": [
            {
                "page_url": PAGE_BLUE,
                "image_url": image_url,
                "disposition": "transcribed",
                "text": "Blue: nozzle 205-225 C",
            }
        ]
    }

    bounded, _ = semantic_runner._bounded_bundle(source_bundle)
    observed_image = bounded["pages"][1]["images"][0]
    assert observed_image["observation"] == {
        "disposition": "transcribed",
        "text": "Blue: nozzle 205-225 C",
    }
    report = semantic_report()
    color_evidence = next(
        item
        for item in report["proposal"]["evidence"]
        if item["field"] == "color_name" and item["key"].endswith(":blue:1.75")
    )
    color_evidence["source_urls"] = [PAGE_BLUE, image_url]
    compiled = compile_report(report, source_bundle, catalog())
    assert "Image review gap" not in compiled.coverage_note


def test_repeated_image_asset_on_one_page_needs_one_observation():
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/repeated-logo.png"
    source_bundle["pages"][1]["images"] = [
        {"url": image_url, "alt": "Logo"},
        {"url": image_url, "alt": "Logo in footer"},
    ]
    source_bundle["pages"][1]["image_count"] = 2
    source_bundle["image_observations"] = {
        "observations": [
            {"page_url": PAGE_BLUE, "image_url": image_url, "disposition": "not_relevant"}
        ]
    }
    _, transcribed, gaps, truncations = semantic_runner._validated_image_observations(source_bundle)
    assert not transcribed
    assert gaps == []
    assert truncations == []


@pytest.mark.parametrize(
    "observation, message",
    [
        ({"page_url": PAGE_WHITE, "image_url": "https://maker.example/media/chart.png", "disposition": "transcribed", "text": "PLA"}, "does not match"),
        ({"page_url": PAGE_BLUE, "image_url": "https://maker.example/media/chart.png", "disposition": "transcribed", "text": "PLA"}, "Duplicate"),
        ({"page_url": PAGE_BLUE, "image_url": "https://maker.example/media/chart.png", "disposition": "transcribed", "text": ""}, "non-empty"),
        ({"page_url": PAGE_BLUE, "image_url": "https://maker.example/media/chart.png", "disposition": "transcribed", "text": "PLA", "extra": "x"}, "Each image observation requires"),
    ],
)
def test_image_observation_rejects_unmatched_duplicate_and_malformed_entries(observation, message):
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/chart.png"
    source_bundle["pages"][1]["images"] = [{"url": image_url}]
    if observation["image_url"] == image_url and observation["page_url"] == PAGE_BLUE:
        source_bundle["image_observations"] = {"observations": [observation, observation]}
    else:
        source_bundle["image_observations"] = {"observations": [observation]}
    with pytest.raises(ValueError, match=message):
        semantic_runner._validated_image_observations(source_bundle)


def test_unreviewed_and_reader_truncated_images_force_partial_coverage():
    source_bundle = deepcopy(bundle())
    source_bundle["pages"][0]["images"] = [
        {"url": "https://maker.example/media/a.png"},
        {"url": "https://maker.example/media/b.png"},
    ]
    source_bundle["pages"][0]["image_count"] = 5
    source_bundle["pages"][0]["images_truncated"] = True
    source_bundle["image_observations"] = {
        "observations": [
            {
                "page_url": PAGE_PRODUCT,
                "image_url": "https://maker.example/media/a.png",
                "disposition": "not_relevant",
            }
        ]
    }
    compiled = compile_report(semantic_report(), source_bundle, catalog())
    assert "Source coverage: partial" in compiled.coverage_note
    assert "Image review gap" in compiled.coverage_note
    assert "truncated the image list" in compiled.coverage_note


@pytest.mark.parametrize("incomplete", ["missing_observation", "truncated_list"])
def test_incomplete_image_review_disables_only_rows_linked_to_its_page(incomplete):
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/blue-chart.png"
    page = next(page for page in source_bundle["pages"] if page["url"] == PAGE_BLUE)
    page["images"] = [{"url": image_url}]
    if incomplete == "missing_observation":
        source_bundle["image_observations"] = {"observations": []}
    else:
        page["image_count"] = 2
        page["images_truncated"] = True
        source_bundle["image_observations"] = {
            "observations": [
                {
                    "page_url": PAGE_BLUE,
                    "image_url": image_url,
                    "disposition": "not_relevant",
                }
            ]
        }

    compiled = compile_report(semantic_report(), source_bundle, catalog())
    rows = {row["filament_key"]: row for row in compiled.draft.filaments}
    assert rows["maker:pla-silk:blue:1.75"]["enabled"] is False
    assert rows["maker:pla-silk:white:1.75"].get("enabled", True) is True
    assert "Source coverage: partial" in compiled.coverage_note


def test_fully_reviewed_not_relevant_image_does_not_disable_linked_row():
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/blue-logo.png"
    page = next(page for page in source_bundle["pages"] if page["url"] == PAGE_BLUE)
    page["images"] = [{"url": image_url}]
    source_bundle["image_observations"] = {
        "observations": [
            {
                "page_url": PAGE_BLUE,
                "image_url": image_url,
                "disposition": "not_relevant",
            }
        ]
    }

    compiled = compile_report(semantic_report(), source_bundle, catalog())
    rows = {row["filament_key"]: row for row in compiled.draft.filaments}
    assert rows["maker:pla-silk:blue:1.75"].get("enabled", True) is True
    assert rows["maker:pla-silk:white:1.75"].get("enabled", True) is True
    assert "Source coverage: complete" in compiled.coverage_note


def test_unobserved_image_url_cannot_be_used_as_evidence():
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/chart.png"
    source_bundle["pages"][1]["images"] = [{"url": image_url}]
    source_bundle["image_observations"] = {"observations": []}
    report = semantic_report()
    color_evidence = next(
        item
        for item in report["proposal"]["evidence"]
        if item["field"] == "color_name" and item["key"].endswith(":blue:1.75")
    )
    color_evidence["source_urls"] = [PAGE_BLUE, image_url]
    with pytest.raises(ValueError, match="outside the fetched manifest"):
        compile_report(report, source_bundle, catalog())


def test_image_evidence_requires_the_matching_page_and_bounds_transcription_size():
    source_bundle = deepcopy(bundle())
    image_url = "https://maker.example/media/chart.png"
    source_bundle["pages"][1]["images"] = [{"url": image_url}]
    source_bundle["image_observations"] = {
        "observations": [
            {
                "page_url": PAGE_BLUE,
                "image_url": image_url,
                "disposition": "transcribed",
                "text": "Color: blue",
            }
        ]
    }
    report = semantic_report()
    color_evidence = next(
        item
        for item in report["proposal"]["evidence"]
        if item["field"] == "color_name" and item["key"].endswith(":blue:1.75")
    )
    color_evidence["source_urls"] = [image_url]
    with pytest.raises(ValueError, match="must also cite its fetched page URL"):
        compile_report(report, source_bundle, catalog())

    source_bundle["image_observations"]["observations"][0]["text"] = "x" * 4_001
    with pytest.raises(ValueError, match="exceeds the 4000-byte limit"):
        semantic_runner._validated_image_observations(source_bundle)


def _batch_fixture(count: int = 4) -> tuple[dict, dict, dict]:
    pages = []
    variants = []
    colors = ["Blue", "White", "Red", "Black"][:count]
    for color in colors:
        url = f"https://maker.example/catalog/pla-{color.casefold()}"
        pages.append(
            {"url": url, "title": f"PLA {color}", "text": f"PLA {color}, 1.75 mm.", "links": []}
        )
        variants.append(
            {
                "filament_key": f"maker:pla:{color.casefold()}:1.75",
                "source_urls": [url],
                "packaging_alias_urls": [],
                "line": "PLA Basic",
                "composition_summary": "PLA",
                "color_summary": color,
                "diameter": 1.75,
                "availability": "discontinued" if color == "Black" else "available",
                "existing_filament_id": None,
                "candidate_ids": [],
                "identity_note": f"Distinct PLA Basic {color} material variant.",
            }
        )
    guidance_url = "https://maker.example/help/pla"
    pages.append(
        {"url": guidance_url, "title": "PLA recommendations", "text": "PLA bed 50 C.", "links": []}
    )
    source_bundle = {
        "manufacturer": {"name": "Maker", "website": "https://maker.example"},
        "pages": pages,
    }
    inventory = {
        "schema_version": 1,
        "coverage": {
            "status": "complete",
            "discovered_urls": [page["url"] for page in pages],
            "reviewed_urls": [page["url"] for page in pages],
            "gaps": [],
            "excluded_sources": [],
        },
        "variants": variants,
        "group_guidance": [
            {
                "guidance_key": "pla-guidance",
                "applies_to_filament_keys": [item["filament_key"] for item in variants],
                "applies_to_all_variants": False,
                "source_urls": [guidance_url],
                "summary": "All PLA variants use a 50 C bed unless a variant page states otherwise.",
            }
        ],
        "issues": [],
    }
    return source_bundle, inventory, catalog()


def _batch_report(source_bundle: dict, inventory: dict, keys: list[str]) -> dict:
    by_key = {item["filament_key"]: item for item in inventory["variants"]}
    brand = {"brand_key": "maker", "mode": "update", "existing_brand": "4", "name": "Maker"}
    rows = []
    identities = []
    brand_source = by_key[keys[0]]["source_urls"][0]
    evidence = _evidence("Brands", "maker", brand, [brand_source])
    reviewed = [source_bundle["pages"][-1]["url"]]
    for key in keys:
        item = by_key[key]
        color = item["color_summary"]
        row = {
            "filament_key": key,
            "brand_key": "maker",
            "mode": "create",
            "name": f"PLA {color}",
            "material_type": "PLA",
            "line": "PLA Basic",
            "color_name": color,
            "diameter": 1.75,
            "recommended_bed_temp_min": 50,
            "availability": item.get("availability") or "available",
        }
        rows.append(row)
        identities.append(
            {
                "filament_key": key,
                "source_urls": item["source_urls"],
                "line": item["line"],
                "composition_summary": item["composition_summary"],
                "color_summary": item["color_summary"],
                "diameter": item["diameter"],
                "packaging_alias_urls": item["packaging_alias_urls"],
                "existing_filament_id": None,
                "match_reason": None,
                "candidate_ids": [],
                "unresolved": False,
            }
        )
        evidence.extend(
            _evidence(
                "Filaments",
                key,
                {
                    field: value
                    for field, value in row.items()
                    if field != "recommended_bed_temp_min"
                },
                item["source_urls"],
            )
        )
        evidence.append(
            {
                "sheet": "Filaments",
                "key": key,
                "field": "recommended_bed_temp_min",
                "kind": "inferred",
                "source_urls": [source_bundle["pages"][-1]["url"]],
                "explanation": "The manufacturer's shared PLA guidance applies to this variant.",
            }
        )
        reviewed.extend(item["source_urls"])
    draft = {
        "filename": "maker.json",
        "brands": [brand],
        "filaments": rows,
        "brand_markets": [],
        "filament_markets": [],
        "presets": [],
    }
    return {
        "schema_version": 1,
        "coverage": {
            "status": "complete",
            "discovered_urls": [p["url"] for p in source_bundle["pages"]],
            "reviewed_urls": list(dict.fromkeys(reviewed)),
            "gaps": [],
            "excluded_sources": [],
        },
        "identities": identities,
        "proposal": {
            "title": "Maker catalog review",
            "draft": draft,
            "evidence": evidence,
            "unmapped_facts": [
                {
                    "filament_key": key,
                    "property_name": "Chemical resistance",
                    "value_summary": "Manufacturer-specific resistance note",
                    "source_urls": by_key[key]["source_urls"][:1],
                }
                for key in keys
            ],
            "source_facts": [
                {
                    "filament_key": key,
                    "property_name": "Bed recommendation",
                    "value_summary": "50 C",
                    "source_urls": by_key[key]["source_urls"][:1],
                    "disposition": "mapped",
                    "mapped_fields": ["recommended_bed_temp_min"],
                }
                for key in keys
            ],
            "coverage_note": "Shared PLA guidance was applied to this batch.",
        },
        "issues": [],
    }


def test_batched_runner_uses_shared_guidance_and_merges_small_variant_batches(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture()
    calls = []

    def fake_reasoner(command, prompt, schema, *, timeout_s):
        calls.append(prompt)
        if "variants" in schema.get("properties", {}):
            return deepcopy(inventory)
        batch_json = prompt.split("INVENTORY_VARIANTS_JSON:\n", 1)[1].split(
            "\n\nGROUP_GUIDANCE_JSON:", 1
        )[0]
        batch_keys = [item["filament_key"] for item in json.loads(batch_json)]
        return _batch_report(source_bundle, inventory, batch_keys)

    monkeypatch.setattr(semantic_runner, "run_reasoner", fake_reasoner)
    proposal = build_batched_proposal(
        ["fake", "{schema}", "{output}"], source_bundle, existing_catalog
    )

    assert len(calls) == 3  # one inventory pass, then 3+1 variants
    assert len(proposal.draft.filaments) == 4
    assert len({row["filament_key"] for row in proposal.draft.filaments}) == 4
    assert len(proposal.draft.brands) == 1
    assert len(proposal.evidence) <= 30  # duplicate brand evidence was merged
    assert len(proposal.unmapped_facts) == 4
    assert len(proposal.source_facts) == 4
    assert {item.filament_key for item in proposal.unmapped_facts} == {
        row["filament_key"] for row in proposal.draft.filaments
    }
    assert (
        next(row for row in proposal.draft.filaments if row["color_name"] == "Black")[
            "availability"
        ]
        == "discontinued"
    )
    assert proposal.coverage_note.find("Source coverage: complete") >= 0


def test_inventory_marks_unreviewed_fetched_page_as_coverage_gap(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture(count=2)
    unread = source_bundle["pages"][1]["url"]
    inventory["coverage"]["reviewed_urls"].remove(unread)

    monkeypatch.setattr(
        semantic_runner,
        "run_reasoner",
        lambda *args, **kwargs: deepcopy(inventory),
    )
    parsed, _ = semantic_runner._inventory_from_reasoner(
        ["fake"], source_bundle, existing_catalog, timeout_s=30
    )

    assert parsed.coverage.status == "partial"
    assert any(str(gap.url) == unread for gap in parsed.coverage.gaps)


def test_inventory_preserves_distinct_keys_with_matching_summary_fields(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture(count=3)
    duplicate = deepcopy(inventory["variants"][1])
    duplicate["filament_key"] = "maker:pla:white:separate-grade"
    duplicate["packaging_alias_urls"] = [PAGE_PRODUCT]
    duplicate["existing_filament_id"] = 99
    source_bundle["pages"].append(
        {
            "url": PAGE_PRODUCT,
            "title": "White spool and sample",
            "text": "Same PLA White material, multiple formats.",
            "links": [],
        }
    )
    inventory["coverage"]["discovered_urls"].append(PAGE_PRODUCT)
    inventory["coverage"]["reviewed_urls"].append(PAGE_PRODUCT)
    inventory["variants"].append(duplicate)
    inventory["group_guidance"][0]["applies_to_filament_keys"].append(duplicate["filament_key"])

    def fake_reasoner(command, prompt, schema, *, timeout_s):
        return deepcopy(inventory)

    monkeypatch.setattr(semantic_runner, "run_reasoner", fake_reasoner)
    report, _ = semantic_runner._inventory_from_reasoner(
        ["fake", "{schema}", "{output}"],
        source_bundle,
        existing_catalog,
        timeout_s=10,
    )

    assert len(report.variants) == 4
    assert report.variants[-1].existing_filament_id == 99


def test_batched_runner_keeps_failed_variant_as_visible_coverage_gap(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture()
    calls = 0

    def fake_reasoner(command, prompt, schema, *, timeout_s):
        nonlocal calls
        calls += 1
        if "variants" in schema.get("properties", {}):
            return deepcopy(inventory)
        if calls == 3:
            raise RuntimeError("synthetic batch failure")
        batch_json = prompt.split("INVENTORY_VARIANTS_JSON:\n", 1)[1].split(
            "\n\nGROUP_GUIDANCE_JSON:", 1
        )[0]
        batch_keys = [item["filament_key"] for item in json.loads(batch_json)]
        return _batch_report(source_bundle, inventory, batch_keys)

    monkeypatch.setattr(semantic_runner, "run_reasoner", fake_reasoner)
    proposal = build_batched_proposal(
        ["fake", "{schema}", "{output}"], source_bundle, existing_catalog
    )

    assert len(proposal.draft.filaments) == 3
    assert "Source coverage: partial" in proposal.coverage_note
    assert "catalog/pla-black" in proposal.coverage_note


def test_incomplete_batch_does_not_discard_other_variant_rows(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture()

    def fake_reasoner(command, prompt, schema, *, timeout_s):
        if "variants" in schema.get("properties", {}):
            return deepcopy(inventory)
        batch_json = prompt.split("INVENTORY_VARIANTS_JSON:\n", 1)[1].split(
            "\n\nGROUP_GUIDANCE_JSON:", 1
        )[0]
        keys = [item["filament_key"] for item in json.loads(batch_json)]
        report = _batch_report(source_bundle, inventory, keys)
        if len(keys) == 1:
            report["proposal"]["draft"]["filaments"] = []
        return report

    monkeypatch.setattr(semantic_runner, "run_reasoner", fake_reasoner)
    proposal = build_batched_proposal(
        ["fake", "{schema}", "{output}"], source_bundle, existing_catalog
    )

    assert len(proposal.draft.filaments) == 3
    assert "Source coverage: partial" in proposal.coverage_note


def test_inventory_drops_unverified_discovered_url_and_marks_gap(monkeypatch):
    source_bundle, inventory, existing_catalog = _batch_fixture(count=1)
    invented = "https://maker.example/not-in-source"
    inventory["coverage"]["discovered_urls"].append(invented)
    inventory["coverage"]["gaps"].append(
        {"url": invented, "reason": "Unverified listing"}
    )

    def fake_reasoner(command, prompt, schema, *, timeout_s):
        return deepcopy(inventory)

    monkeypatch.setattr(semantic_runner, "run_reasoner", fake_reasoner)
    report, _ = semantic_runner._inventory_from_reasoner(
        ["fake", "{schema}", "{output}"],
        source_bundle,
        existing_catalog,
        timeout_s=10,
    )

    assert invented not in [str(url) for url in report.coverage.discovered_urls]
    assert report.coverage.status == "partial"
    assert any("outside the source manifest" in gap.reason for gap in report.coverage.gaps)
    assert invented not in [str(gap.url) for gap in report.coverage.gaps]


def test_batch_omits_price_packaging_and_verification_even_with_evidence():
    source_bundle, inventory, _ = _batch_fixture(count=1)
    report = _batch_report(
        source_bundle, inventory, [inventory["variants"][0]["filament_key"]]
    )
    brand = report["proposal"]["draft"]["brands"][0]
    filament = report["proposal"]["draft"]["filaments"][0]
    brand["verified"] = True
    filament["price"] = "100"
    filament["spool_weight"] = 1000
    parsed = semantic_runner.SemanticReport.model_validate(report)

    semantic_runner._omit_batch_fields_without_evidence(parsed)

    assert "verified" not in parsed.proposal.draft.brands[0]
    assert "price" not in parsed.proposal.draft.filaments[0]
    assert "spool_weight" not in parsed.proposal.draft.filaments[0]
    assert sum(item.kind == "unsupported" for item in parsed.issues) >= 3
