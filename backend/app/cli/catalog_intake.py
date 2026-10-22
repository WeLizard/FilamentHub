"""Build a reviewable catalog proposal from manufacturer sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.services.catalog_intake_snapshot import collect_catalog_snapshot
from app.services.catalog_semantic_runner import (
    build_batched_proposal,
    parse_reasoner_command,
)
from app.services.catalog_source_reader import read_source_site


class SubmissionUnknownError(RuntimeError):
    """The server may have saved the proposal; the request must not be retried."""


def _api_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API origin must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("API origin must not contain a path")
    if parsed.scheme == "https" and parsed.hostname:
        return value.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return value.rstrip("/")
    raise ValueError("API origin must use HTTPS, or HTTP on loopback")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", action="append", required=True)
    parser.add_argument("--brand-name", required=True)
    parser.add_argument("--brand-id", type=int)
    parser.add_argument("--api-origin")
    parser.add_argument("--reasoner-command", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--image-observations",
        type=Path,
        help="F: JSON file with explicit observations for source-page images",
    )
    parser.add_argument("--submit", action="store_true")
    return parser


async def build_proposal(args: argparse.Namespace) -> dict:
    if len(args.source_url) > 120:
        raise ValueError("At most 120 agent-selected source URLs may be read")
    if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
        raise ValueError("timeout-seconds must be between 1 and 3600")
    configured_origin = _api_origin(os.environ.get("FH_CATALOG_API_ORIGIN", "http://127.0.0.1:8001"))
    origin = _api_origin(args.api_origin or configured_origin)
    if origin != configured_origin:
        raise ValueError("API origin must match FH_CATALOG_API_ORIGIN")
    async with httpx.AsyncClient(base_url=origin, timeout=30.0) as client:
        catalog = await collect_catalog_snapshot(client, args.brand_name, args.brand_id)
    if args.brand_id is not None and catalog.get("selected_brand") is None:
        raise ValueError("The requested existing brand ID was not found")
    # The curator chooses the evidence pages. The reader only retrieves those
    # exact entries; it does not choose additional pages from site navigation.
    source = await read_source_site(args.source_url, max_pages=len(args.source_url))
    bundle = json.loads(json.dumps(source.model_dump(), ensure_ascii=False))
    if not bundle.get("pages"):
        raise ValueError("No permitted source page could be read")
    if args.image_observations is not None:
        observations_path = args.image_observations.resolve()
        if os.name == "nt" and observations_path.drive.casefold() != "f:":
            raise ValueError("Image observations must be read from F:")
        try:
            size = observations_path.stat().st_size
            if size > 512 * 1024:
                raise ValueError("Image observations exceed the 524288-byte limit")
            raw_observations = observations_path.read_text(encoding="utf-8")
        except ValueError:
            raise
        except (OSError, UnicodeError) as exc:
            raise ValueError("Image observations must be a readable UTF-8 JSON file") from exc
        if size > 512 * 1024 or len(raw_observations.encode("utf-8")) > 512 * 1024:
            raise ValueError("Image observations exceed the 524288-byte limit")
        try:
            bundle["image_observations"] = json.loads(raw_observations)
        except json.JSONDecodeError as exc:
            raise ValueError("Image observations must be valid JSON") from exc
    proposal = await asyncio.to_thread(
        build_batched_proposal,
        parse_reasoner_command(args.reasoner_command),
        bundle,
        catalog,
        timeout_s=args.timeout_seconds,
    )
    payload = proposal.model_dump(mode="json")
    if args.output is not None:
        if os.name == "nt" and args.output.resolve().drive.casefold() != "f:":
            raise ValueError("Proposal output must be placed on F:")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.submit:
        token = os.environ.get("FH_CATALOG_SERVICE_TOKEN", "")
        if not token:
            raise ValueError("FH_CATALOG_SERVICE_TOKEN is required for submission")
        async with httpx.AsyncClient(base_url=origin, timeout=30.0) as client:
            try:
                response = await client.post(
                    "/api/v1/service/catalog/curation/proposals",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as exc:
                raise SubmissionUnknownError(
                    "Proposal submission outcome is unknown; inspect the catalog center before a new submission"
                ) from exc
            response.raise_for_status()
            saved = response.json()
            return {"proposal_id": saved["id"], "revision": saved["revision"]}
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(build_proposal(args))
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.output is not None and not args.submit:
        print(
            json.dumps({"output": str(args.output), "title": result["title"]}, ensure_ascii=False)
        )
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
