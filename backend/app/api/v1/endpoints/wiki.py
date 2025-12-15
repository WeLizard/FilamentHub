"""Wiki API endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_current_admin_user
from app.db.session import get_db
from app.models.user import User
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory
from app.schemas.wiki import (
    WikiArticleCreate,
    WikiArticleListResponse,
    WikiArticleResponse,
    WikiArticleSummary,
    WikiArticleUpdate,
    WikiCategoryCreate,
    WikiCategoryListResponse,
    WikiCategoryResponse,
    WikiCategoryUpdate,
)

router = APIRouter(prefix="/wiki", tags=["wiki"])


# ============================================================================
# Wiki Categories
# ============================================================================

@router.get("/categories", response_model=WikiCategoryListResponse)
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
) -> WikiCategoryListResponse:
    """
    Получить список всех категорий Wiki.
    
    Возвращает категории отсортированные по полю order.
    """
    # Подсчет общего количества
    count_result = await db.execute(select(func.count(WikiCategory.id)))
    total = count_result.scalar_one()
    
    # Получение категорий с подсчетом опубликованных статей
    query = (
        select(
            WikiCategory,
            func.count(WikiArticle.id).label("articles_count")
        )
        .outerjoin(WikiArticle, (WikiArticle.category_id == WikiCategory.id) & (WikiArticle.status == WikiArticleStatus.PUBLISHED))
        .group_by(WikiCategory.id)
        .order_by(WikiCategory.order.asc(), WikiCategory.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Формируем ответ
    categories = []
    for category, articles_count in rows:
        category_dict = {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "icon": category.icon,
            "order": category.order,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
            "articles_count": articles_count or 0,
        }
        categories.append(WikiCategoryResponse(**category_dict))
    
    return WikiCategoryListResponse(
        items=categories,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/categories/{category_slug}", response_model=WikiCategoryResponse)
async def get_category(
    category_slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WikiCategoryResponse:
    """Получить категорию по slug."""
    # Получаем категорию с подсчетом опубликованных статей
    query = (
        select(
            WikiCategory,
            func.count(WikiArticle.id).label("articles_count")
        )
        .outerjoin(WikiArticle, (WikiArticle.category_id == WikiCategory.id) & (WikiArticle.status == WikiArticleStatus.PUBLISHED))
        .where(WikiCategory.slug == category_slug)
        .group_by(WikiCategory.id)
    )
    
    result = await db.execute(query)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category, articles_count = row
    
    return WikiCategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        order=category.order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        articles_count=articles_count or 0,
    )


@router.post("/categories", response_model=WikiCategoryResponse)
async def create_category(
    data: WikiCategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> WikiCategoryResponse:
    """Создать новую категорию (только для администраторов)."""
    # Проверка уникальности slug
    existing = await db.execute(
        select(WikiCategory).where(
            (WikiCategory.slug == data.slug) | (WikiCategory.name == data.name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category with this slug or name already exists")
    
    # Создание категории
    category = WikiCategory(**data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    
    return WikiCategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        order=category.order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        articles_count=0,
    )


@router.patch("/categories/{category_id}", response_model=WikiCategoryResponse)
async def update_category(
    category_id: int,
    data: WikiCategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> WikiCategoryResponse:
    """Обновить категорию (только для администраторов)."""
    result = await db.execute(select(WikiCategory).where(WikiCategory.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Обновление полей
    update_data = data.model_dump(exclude_unset=True)
    
    # Проверка уникальности slug если он изменяется
    if "slug" in update_data and update_data["slug"] != category.slug:
        existing = await db.execute(
            select(WikiCategory).where(WikiCategory.slug == update_data["slug"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category with this slug already exists")
    
    # Проверка уникальности name если он изменяется
    if "name" in update_data and update_data["name"] != category.name:
        existing = await db.execute(
            select(WikiCategory).where(WikiCategory.name == update_data["name"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category with this name already exists")
    
    for field, value in update_data.items():
        setattr(category, field, value)
    
    await db.commit()
    await db.refresh(category)
    
    # Получаем количество статей
    count_result = await db.execute(
        select(func.count(WikiArticle.id)).where(
            (WikiArticle.category_id == category.id) & (WikiArticle.status == WikiArticleStatus.PUBLISHED)
        )
    )
    articles_count = count_result.scalar_one()
    
    return WikiCategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        order=category.order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        articles_count=articles_count,
    )


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Удалить категорию (только для администраторов)."""
    result = await db.execute(select(WikiCategory).where(WikiCategory.id == category_id))
    category = result.scalar_one_or_none()
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    await db.delete(category)
    await db.commit()
    
    return {"message": "Category deleted successfully"}


# ============================================================================
# Wiki Articles
# ============================================================================

@router.get("/articles", response_model=WikiArticleListResponse)
async def list_articles(
    db: Annotated[AsyncSession, Depends(get_db)],
    category_slug: str | None = Query(None, description="Filter by category slug"),
    search: str | None = Query(None, description="Search in title, summary, and tags"),
    published_only: bool = Query(True, description="Show only published articles"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> WikiArticleListResponse:
    """
    Получить список статей с фильтрацией и поиском.
    
    - **category_slug**: фильтр по категории
    - **search**: поиск по заголовку, краткому описанию и тегам
    - **published_only**: показывать только опубликованные статьи
    """
    # Базовый запрос
    query = select(WikiArticle)
    
    # Фильтр по категории
    if category_slug:
        category_result = await db.execute(
            select(WikiCategory.id).where(WikiCategory.slug == category_slug)
        )
        category_id = category_result.scalar_one_or_none()
        if not category_id:
            raise HTTPException(status_code=404, detail="Category not found")
        query = query.where(WikiArticle.category_id == category_id)
    
    # Фильтр по публикации
    if published_only:
        query = query.where(WikiArticle.status == WikiArticleStatus.PUBLISHED)
    
    # Поиск
    if search:
        search_pattern = f"%{search}%"
        # tags это JSON поле, поэтому используем cast для поиска
        from sqlalchemy import cast, String
        query = query.where(
            or_(
                WikiArticle.title.ilike(search_pattern),
                WikiArticle.summary.ilike(search_pattern),
                cast(WikiArticle.tags, String).ilike(search_pattern),
            )
        )
    
    # Подсчет total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()
    
    # Сортировка и пагинация
    query = (
        query
        .order_by(WikiArticle.order.asc(), WikiArticle.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    
    result = await db.execute(query)
    articles = result.scalars().all()
    
    # Конвертируем статьи в Summary, добавляя published поле из status
    items = []
    for article in articles:
        article_dict = {
            "id": article.id,
            "category_id": article.category_id,
            "title": article.title,
            "slug": article.slug,
            "summary": article.summary,
            "tags": article.tags,
            "author": article.author,
            "published": article.status == WikiArticleStatus.PUBLISHED,
            "views": article.views,
            "order": article.order,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
        }
        items.append(WikiArticleSummary(**article_dict))
    
    return WikiArticleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/articles/{article_slug}", response_model=WikiArticleResponse)
async def get_article(
    article_slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WikiArticleResponse:
    """
    Получить статью по slug.
    
    Автоматически увеличивает счетчик просмотров.
    """
    result = await db.execute(
        select(WikiArticle).where(WikiArticle.slug == article_slug)
    )
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    if article.status != WikiArticleStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Article not published")
    
    # Увеличиваем счетчик просмотров
    article.views += 1
    await db.commit()
    await db.refresh(article)
    
    # Получаем имя категории
    category_result = await db.execute(
        select(WikiCategory.name).where(WikiCategory.id == article.category_id)
    )
    category_name = category_result.scalar_one_or_none()
    
    article_dict = {
        "id": article.id,
        "category_id": article.category_id,
        "title": article.title,
        "slug": article.slug,
        "summary": article.summary,
        "content": article.content,
        "tags": article.tags,
        "author": article.author,
        "published": article.status == WikiArticleStatus.PUBLISHED,
        "views": article.views,
        "order": article.order,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
        "category_name": category_name,
    }
    
    return WikiArticleResponse(**article_dict)


@router.post("/articles", response_model=WikiArticleResponse)
async def create_article(
    data: WikiArticleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> WikiArticleResponse:
    """Создать новую статью (только для администраторов)."""
    # Проверка существования категории
    category_result = await db.execute(
        select(WikiCategory).where(WikiCategory.id == data.category_id)
    )
    category = category_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Проверка уникальности slug
    existing = await db.execute(
        select(WikiArticle).where(WikiArticle.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Article with this slug already exists")
    
    # Создание статьи
    article_data = data.model_dump()
    # Конвертируем published bool в status enum
    if "published" in article_data:
        article_data["status"] = WikiArticleStatus.PUBLISHED if article_data.pop("published") else WikiArticleStatus.DRAFT
    article = WikiArticle(**article_data)
    article.created_by_id = _current_user.id
    article.updated_by_id = _current_user.id
    db.add(article)
    await db.commit()
    await db.refresh(article)
    
    return WikiArticleResponse(
        id=article.id,
        category_id=article.category_id,
        title=article.title,
        slug=article.slug,
        summary=article.summary,
        content=article.content,
        tags=article.tags,
        author=article.author,
        published=article.status == WikiArticleStatus.PUBLISHED,
        views=article.views,
        order=article.order,
        created_at=article.created_at,
        updated_at=article.updated_at,
        category_name=category.name,
    )


@router.patch("/articles/{article_id}", response_model=WikiArticleResponse)
async def update_article(
    article_id: int,
    data: WikiArticleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> WikiArticleResponse:
    """Обновить статью (только для администраторов)."""
    result = await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Обновление полей
    update_data = data.model_dump(exclude_unset=True)
    
    # Конвертируем published bool в status enum
    if "published" in update_data:
        update_data["status"] = WikiArticleStatus.PUBLISHED if update_data.pop("published") else WikiArticleStatus.DRAFT
    
    # Проверка существования новой категории
    if "category_id" in update_data:
        category_result = await db.execute(
            select(WikiCategory).where(WikiCategory.id == update_data["category_id"])
        )
        if not category_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Category not found")
    
    # Проверка уникальности slug если он изменяется
    if "slug" in update_data and update_data["slug"] != article.slug:
        existing = await db.execute(
            select(WikiArticle).where(WikiArticle.slug == update_data["slug"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Article with this slug already exists")
    
    # Обновляем поля
    for field, value in update_data.items():
        setattr(article, field, value)
    
    # Обновляем updated_by_id
    article.updated_by_id = _current_user.id
    
    await db.commit()
    await db.refresh(article)
    
    # Получаем имя категории
    category_result = await db.execute(
        select(WikiCategory.name).where(WikiCategory.id == article.category_id)
    )
    category_name = category_result.scalar_one_or_none()
    
    return WikiArticleResponse(
        id=article.id,
        category_id=article.category_id,
        title=article.title,
        slug=article.slug,
        summary=article.summary,
        content=article.content,
        tags=article.tags,
        author=article.author,
        published=article.status == WikiArticleStatus.PUBLISHED,
        views=article.views,
        order=article.order,
        created_at=article.created_at,
        updated_at=article.updated_at,
        category_name=category_name,
    )


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Удалить статью (только для администраторов)."""
    result = await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
    article = result.scalar_one_or_none()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    await db.delete(article)
    await db.commit()
    
    return {"message": "Article deleted successfully"}


# ============================================================================
# Search
# ============================================================================

@router.get("/search", response_model=WikiArticleListResponse)
async def search_articles(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> WikiArticleListResponse:
    """
    Полнотекстовый поиск по статьям.
    
    Ищет в заголовке, summary, content и тегах.
    """
    search_pattern = f"%{q}%"
    
    # tags это JSON поле, поэтому используем cast для поиска
    from sqlalchemy import cast, String
    query = select(WikiArticle).where(
        WikiArticle.status == WikiArticleStatus.PUBLISHED,
        or_(
            WikiArticle.title.ilike(search_pattern),
            WikiArticle.summary.ilike(search_pattern),
            WikiArticle.content.ilike(search_pattern),
            cast(WikiArticle.tags, String).ilike(search_pattern),
        )
    )
    
    # Подсчет total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()
    
    # Сортировка по relevance (title > summary > content)
    # Для простоты сортируем по дате, можно добавить полнотекстовый поиск PostgreSQL
    query = (
        query
        .order_by(WikiArticle.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    
    result = await db.execute(query)
    articles = result.scalars().all()
    
    # Конвертируем статьи в Summary, добавляя published поле из status
    items = []
    for article in articles:
        article_dict = {
            "id": article.id,
            "category_id": article.category_id,
            "title": article.title,
            "slug": article.slug,
            "summary": article.summary,
            "tags": article.tags,
            "author": article.author,
            "published": article.status == WikiArticleStatus.PUBLISHED,
            "views": article.views,
            "order": article.order,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
        }
        items.append(WikiArticleSummary(**article_dict))
    
    return WikiArticleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )

