"""Service for syncing Wiki content from Markdown files to database."""

import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from Markdown content."""
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if not match:
        return {}, content

    yaml_content = match.group(1)
    markdown_content = match.group(2)

    try:
        metadata = yaml.safe_load(yaml_content)
        return metadata or {}, markdown_content
    except yaml.YAMLError:
        return {}, content


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
        category = WikiCategory(
            name=category_name or category_slug.replace("_", " ").title(),
            slug=category_slug,
            icon=get_category_icon(category_slug),
            description=get_category_description(category_slug)
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)

    return category


async def sync_article(
    db: AsyncSession,
    file_path: Path,
    content: str,
    metadata: dict[str, Any]
) -> dict[str, Any]:
    """Sync single article to database. Returns result dict."""
    title = metadata.get("title")
    category_slug = metadata.get("category")
    slug = metadata.get("slug")

    if not all([title, category_slug, slug]):
        return {
            "file": file_path.name,
            "status": "skipped",
            "reason": "missing required metadata (title, category, or slug)"
        }

    category = await get_or_create_category(db, category_slug)

    result = await db.execute(
        select(WikiArticle).where(WikiArticle.slug == slug)
    )
    article = result.scalar_one_or_none()

    # Parse tags
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    tags_json = tags if tags else None

    # Parse status
    status_str = metadata.get("status", "draft")
    try:
        status = WikiArticleStatus(status_str)
    except ValueError:
        status = WikiArticleStatus.DRAFT

    author_id = metadata.get("author_id", 1)

    # Generate summary
    summary_text = content.replace("#", "").strip()
    summary = summary_text[:200] + "..." if len(summary_text) > 200 else summary_text

    action = "updated" if article else "created"

    if article:
        article.title = title
        article.summary = summary
        article.content = content
        article.category_id = category.id
        article.tags = tags_json
        article.status = status
        article.updated_by_id = author_id
    else:
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

    await db.commit()

    return {
        "file": file_path.name,
        "status": action,
        "title": title,
        "slug": slug,
        "category": category_slug
    }


def generate_frontmatter(article: "WikiArticle", category_slug: str) -> str:
    """Generate YAML frontmatter string from article data."""
    tags_str = ""
    if article.tags:
        tags_list = ', '.join(f'"{t}"' for t in article.tags)
        tags_str = f"[{tags_list}]"
    else:
        tags_str = "[]"

    lines = [
        "---",
        f'title: "{article.title}"',
        f"category: {category_slug}",
        f"slug: {article.slug}",
        f"tags: {tags_str}",
        f"status: {article.status.value}",
        f"author_id: {article.created_by_id or 1}",
        "---",
    ]
    return "\n".join(lines)


async def export_article_to_markdown(
    db: AsyncSession,
    article_id: int,
) -> tuple[str | None, str | None]:
    """Export single article to markdown string. Returns (filename, content) or (None, None)."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(WikiArticle)
        .where(WikiArticle.id == article_id)
        .options(selectinload(WikiArticle.category))
    )
    article = result.scalar_one_or_none()

    if not article:
        return None, None

    category_slug = article.category.slug if article.category else "uncategorized"
    frontmatter = generate_frontmatter(article, category_slug)
    content = f"{frontmatter}\n{article.content}"
    filename = f"{article.slug}.md"

    return filename, content


async def export_articles_to_markdown(db: AsyncSession) -> dict[str, Any]:
    """
    Export all articles from DB to .md files in wiki_content/.

    Returns dict with export results.
    """
    from sqlalchemy.orm import selectinload

    backend_dir = Path(__file__).parent.parent.parent
    wiki_content_path = backend_dir / "wiki_content"

    result = await db.execute(
        select(WikiArticle).options(selectinload(WikiArticle.category))
    )
    articles = result.scalars().all()

    if not articles:
        return {
            "success": True,
            "message": "No articles found in database",
            "exported": 0,
            "errors": 0,
            "details": [],
        }

    results: dict[str, Any] = {
        "success": True,
        "message": "",
        "exported": 0,
        "errors": 0,
        "details": [],
    }

    for article in articles:
        try:
            category_slug = article.category.slug if article.category else "uncategorized"
            category_dir = wiki_content_path / category_slug
            category_dir.mkdir(parents=True, exist_ok=True)

            frontmatter = generate_frontmatter(article, category_slug)
            file_content = f"{frontmatter}\n{article.content}"

            file_path = category_dir / f"{article.slug}.md"
            file_path.write_text(file_content, encoding="utf-8")

            results["exported"] += 1
            results["details"].append({
                "file": f"{category_slug}/{article.slug}.md",
                "status": "exported",
                "title": article.title,
            })
        except Exception as e:
            results["errors"] += 1
            results["details"].append({
                "file": article.slug,
                "status": "error",
                "reason": str(e),
            })

    results["message"] = (
        f"Export complete: {results['exported']} files written"
    )
    if results["errors"] > 0:
        results["message"] += f", {results['errors']} errors"

    return results


async def sync_wiki_from_markdown(db: AsyncSession) -> dict[str, Any]:
    """
    Sync all Markdown files from wiki_content/ to database.

    Returns dict with sync results.
    """
    # Get wiki_content path
    backend_dir = Path(__file__).parent.parent.parent  # services -> app -> backend
    wiki_content_path = backend_dir / "wiki_content"

    if not wiki_content_path.exists():
        return {
            "success": False,
            "message": f"Wiki content directory not found: {wiki_content_path}",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "details": []
        }

    # Find all .md files
    md_files = list(wiki_content_path.rglob("*.md"))

    if not md_files:
        return {
            "success": True,
            "message": "No Markdown files found in wiki_content/",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "details": []
        }

    results = {
        "success": True,
        "message": "",
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }

    for file_path in sorted(md_files):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, markdown_content = parse_frontmatter(content)

            result = await sync_article(db, file_path, markdown_content, metadata)
            results["details"].append(result)

            if result["status"] == "created":
                results["created"] += 1
            elif result["status"] == "updated":
                results["updated"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1

        except Exception as e:
            results["errors"] += 1
            results["details"].append({
                "file": file_path.name,
                "status": "error",
                "reason": str(e)
            })

    total = results["created"] + results["updated"]
    results["message"] = f"Синхронизация завершена: {total} статей обработано ({results['created']} создано, {results['updated']} обновлено)"

    if results["errors"] > 0:
        results["message"] += f", {results['errors']} ошибок"

    return results
