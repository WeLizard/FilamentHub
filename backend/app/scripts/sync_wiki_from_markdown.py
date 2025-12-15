#!/usr/bin/env python3
"""
Sync Wiki content from Markdown files to database.

Usage:
    python -m app.scripts.sync_wiki_from_markdown
"""

import asyncio
import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse YAML frontmatter from Markdown content.
    
    Returns:
        Tuple of (metadata dict, markdown content without frontmatter)
    """
    # Check for YAML frontmatter (--- at start)
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if not match:
        return {}, content
    
    yaml_content = match.group(1)
    markdown_content = match.group(2)
    
    try:
        metadata = yaml.safe_load(yaml_content)
        return metadata or {}, markdown_content
    except yaml.YAMLError as e:
        print(f"⚠️  YAML parsing error: {e}")
        return {}, content


async def get_or_create_category(
    db: AsyncSession, 
    category_slug: str,
    category_name: str | None = None
) -> WikiCategory:
    """Get existing category or create new one."""
    result = await db.execute(
        select(WikiCategory).where(WikiCategory.slug == category_slug)
    )
    category = result.scalar_one_or_none()
    
    if not category:
        # Create new category
        category = WikiCategory(
            name=category_name or category_slug.replace("_", " ").title(),
            slug=category_slug,
            icon=get_category_icon(category_slug),
            description=get_category_description(category_slug)
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)
        print(f"  ✅ Created category: {category.name} ({category.slug})")
    
    return category


def get_category_icon(slug: str) -> str:
    """Get icon for category based on slug."""
    icons = {
        "materials": "🧵",
        "troubleshooting": "🔧",
        "beginners": "🎓",
        "advanced": "🚀",
        "software": "💻",
    }
    return icons.get(slug, "📄")


def get_category_description(slug: str) -> str:
    """Get description for category based on slug."""
    descriptions = {
        "materials": "Свойства, применение и характеристики материалов для 3D-печати",
        "troubleshooting": "Решение типичных проблем и дефектов 3D-печати",
        "beginners": "Руководства и инструкции для начинающих",
        "advanced": "Продвинутые техники и настройки",
        "software": "Программное обеспечение для моделирования и слайсинга",
    }
    return descriptions.get(slug, "")


async def sync_article(
    db: AsyncSession,
    file_path: Path,
    content: str,
    metadata: dict[str, Any]
) -> None:
    """Sync single article to database."""
    # Extract required fields
    title = metadata.get("title")
    category_slug = metadata.get("category")
    slug = metadata.get("slug")
    
    if not all([title, category_slug, slug]):
        print(f"  ⚠️  Skipping {file_path.name}: missing required metadata (title, category, or slug)")
        return
    
    # Get or create category
    category = await get_or_create_category(db, category_slug)
    
    # Check if article exists
    result = await db.execute(
        select(WikiArticle).where(WikiArticle.slug == slug)
    )
    article = result.scalar_one_or_none()
    
    # Parse tags (can be list or comma-separated string)
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    # Convert to JSON string for database (tags field is String, not JSON)
    import json
    tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
    
    # Parse status
    status_str = metadata.get("status", "draft")
    try:
        status = WikiArticleStatus(status_str)
    except ValueError:
        status = WikiArticleStatus.DRAFT
    
    # Get author_id (default to 1 = admin)
    author_id = metadata.get("author_id", 1)
    
    # Generate summary from first 200 chars of content (strip markdown headers)
    summary_text = content.replace("#", "").strip()
    summary = summary_text[:200] + "..." if len(summary_text) > 200 else summary_text
    
    if article:
        # Update existing
        article.title = title
        article.summary = summary
        article.content = content
        article.category_id = category.id
        article.tags = tags_json
        article.status = status
        article.updated_by_id = author_id
        print(f"  ✅ Updated article: {title} ({slug})")
    else:
        # Create new
        article = WikiArticle(
            title=title,
            slug=slug,
            summary=summary,
            content=content,
            category_id=category.id,
            tags=tags_json,
            status=status,
            created_by_id=author_id,
            updated_by_id=author_id
        )
        db.add(article)
        print(f"  ✅ Created article: {title} ({slug})")
    
    await db.commit()


async def sync_all_articles() -> None:
    """Sync all Markdown files from wiki_content/ to database."""
    # Get path relative to backend directory
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent.parent  # backend/app/scripts -> backend
    wiki_content_path = backend_dir / "wiki_content"
    
    # Debug: print paths
    print(f"Script dir: {script_dir}")
    print(f"Backend dir: {backend_dir}")
    print(f"Wiki content path: {wiki_content_path}")
    print(f"Wiki content exists: {wiki_content_path.exists()}")
    
    if not wiki_content_path.exists():
        print(f"❌ Wiki content directory not found: {wiki_content_path}")
        return
    
    print(f"📚 Syncing Wiki content from {wiki_content_path}\n")
    
    # Find all .md files
    md_files = list(wiki_content_path.rglob("*.md"))
    
    if not md_files:
        print("⚠️  No Markdown files found in wiki_content/")
        return
    
    print(f"Found {len(md_files)} Markdown files\n")
    
    async with AsyncSessionLocal() as db:
        for file_path in sorted(md_files):
            print(f"📄 Processing: {file_path.relative_to(wiki_content_path)}")
            
            try:
                content = file_path.read_text(encoding="utf-8")
                metadata, markdown_content = parse_frontmatter(content)
                
                await sync_article(db, file_path, markdown_content, metadata)
                
            except Exception as e:
                print(f"  ❌ Error processing {file_path.name}: {e}")
                continue
    
    print(f"\n✅ Sync complete! Processed {len(md_files)} files")


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

