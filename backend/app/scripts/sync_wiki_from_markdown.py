#!/usr/bin/env python3
"""
Sync Wiki content from Markdown files to database.

Usage:
    python -m app.scripts.sync_wiki_from_markdown
"""

import asyncio

from app.db.session import AsyncSessionLocal
from app.services.wiki_sync_service import sync_wiki_from_markdown


async def sync_all_articles() -> None:
    """Run the canonical versioned Wiki synchronization service."""
    async with AsyncSessionLocal() as db:
        result = await sync_wiki_from_markdown(db)

    print(result["message"])
    for detail in result["details"]:
        reason = f": {detail['reason']}" if detail.get("reason") else ""
        print(f"[{detail['status']}] {detail['file']}{reason}")


async def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("Wiki Markdown → Database Sync")
    print("=" * 60)
    print()

    try:
        print("DEBUG: Starting sync_all_articles()")
        await sync_all_articles()
        print("DEBUG: sync_all_articles() completed")
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
