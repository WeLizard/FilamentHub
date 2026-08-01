"""Validate active or staged file-backed legal editions."""

from __future__ import annotations

import argparse
import sys

from app.services.legal_document_service import (
    CONTENT_ROOT,
    LegalContentError,
    load_legal_catalog,
    validate_legal_edition,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate FilamentHub legal manifests and Markdown files."
    )
    parser.add_argument(
        "--edition",
        action="append",
        default=[],
        help="Validate a staged edition id even when it is not active yet.",
    )
    args = parser.parse_args()

    try:
        catalog = load_legal_catalog(CONTENT_ROOT)
        active = ", ".join(
            f"{pack.value}={edition.edition_id}"
            for pack, edition in catalog.packs.items()
        )
        print(f"Active legal catalog is valid: {active}")
        for edition_id in args.edition:
            edition = validate_legal_edition(edition_id, CONTENT_ROOT)
            print(
                f"Staged edition is valid: {edition.edition_id} "
                f"({len(edition.documents)} documents)"
            )
    except LegalContentError as exc:
        print(f"Legal content validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
