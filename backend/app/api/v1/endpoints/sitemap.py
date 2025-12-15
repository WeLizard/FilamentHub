"""Sitemap.xml endpoint для SEO."""

from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.filament import Filament
from app.models.brand import Brand
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory

router = APIRouter(tags=["seo"])


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_xml(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Генерирует sitemap.xml для поисковых роботов.
    
    Включает:
    - Главную страницу
    - Каталог материалов
    - Страницы филаментов
    - Страницы брендов
    - Wiki категории
    - Wiki статьи
    """
    base_url = "https://filamenthub.ru"
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Начинаем формировать XML
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9',
        '         http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">',
    ]
    
    # Статические страницы
    static_pages = [
        ("/", "1.0", "daily"),
        ("/wiki", "0.9", "weekly"),
        ("/download", "0.8", "monthly"),
    ]
    
    for path, priority, changefreq in static_pages:
        xml_lines.append(f'  <url>')
        xml_lines.append(f'    <loc>{base_url}{path}</loc>')
        xml_lines.append(f'    <lastmod>{current_date}</lastmod>')
        xml_lines.append(f'    <changefreq>{changefreq}</changefreq>')
        xml_lines.append(f'    <priority>{priority}</priority>')
        xml_lines.append(f'  </url>')
    
    # Филаменты
    filaments_result = await db.execute(select(Filament.id))
    filaments = filaments_result.scalars().all()
    
    for filament_id in filaments:
        xml_lines.append(f'  <url>')
        xml_lines.append(f'    <loc>{base_url}/filaments/{filament_id}</loc>')
        xml_lines.append(f'    <lastmod>{current_date}</lastmod>')
        xml_lines.append(f'    <changefreq>weekly</changefreq>')
        xml_lines.append(f'    <priority>0.8</priority>')
        xml_lines.append(f'  </url>')
    
    # Бренды
    brands_result = await db.execute(select(Brand.id))
    brands = brands_result.scalars().all()
    
    for brand_id in brands:
        xml_lines.append(f'  <url>')
        xml_lines.append(f'    <loc>{base_url}/brands/{brand_id}</loc>')
        xml_lines.append(f'    <lastmod>{current_date}</lastmod>')
        xml_lines.append(f'    <changefreq>monthly</changefreq>')
        xml_lines.append(f'    <priority>0.7</priority>')
        xml_lines.append(f'  </url>')
    
    # Wiki категории
    categories_result = await db.execute(select(WikiCategory.slug))
    categories = categories_result.scalars().all()
    
    for category_slug in categories:
        xml_lines.append(f'  <url>')
        xml_lines.append(f'    <loc>{base_url}/wiki/{category_slug}</loc>')
        xml_lines.append(f'    <lastmod>{current_date}</lastmod>')
        xml_lines.append(f'    <changefreq>weekly</changefreq>')
        xml_lines.append(f'    <priority>0.8</priority>')
        xml_lines.append(f'  </url>')
    
    # Wiki статьи (только опубликованные)
    articles_result = await db.execute(
        select(WikiArticle.slug, WikiArticle.updated_at).where(
            WikiArticle.status == WikiArticleStatus.PUBLISHED
        )
    )
    articles = articles_result.all()
    
    for article_slug, updated_at in articles:
        lastmod = updated_at.strftime("%Y-%m-%d") if updated_at else current_date
        xml_lines.append(f'  <url>')
        xml_lines.append(f'    <loc>{base_url}/wiki/articles/{article_slug}</loc>')
        xml_lines.append(f'    <lastmod>{lastmod}</lastmod>')
        xml_lines.append(f'    <changefreq>monthly</changefreq>')
        xml_lines.append(f'    <priority>0.9</priority>')
        xml_lines.append(f'  </url>')
    
    # Закрываем XML
    xml_lines.append('</urlset>')
    
    xml_content = '\n'.join(xml_lines)
    
    return PlainTextResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Type": "application/xml; charset=utf-8"},
    )

