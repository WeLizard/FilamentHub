"""Critical invariants for versioned Wiki authoring."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.user import UserRole
from app.models.wiki_article import WikiArticle, WikiArticleProvenance
from app.models.wiki_category import WikiCategory
from app.models.wiki_revision import WikiRevision, WikiRevisionStatus
from app.models.wiki_space import WikiSpace
from app.services.account_deletion import delete_user_account
from app.services.wiki_sync_service import sync_article

pytestmark = pytest.mark.asyncio


async def _seed_wiki(db_session) -> WikiCategory:
    db_session.add_all(
        [
            WikiSpace(
                id=1,
                key="guides",
                order=0,
                allows_community_authors=False,
            ),
            WikiSpace(
                id=2,
                key="knowledge",
                order=10,
                allows_community_authors=True,
            ),
        ]
    )
    category = WikiCategory(
        name="Materials",
        slug="materials",
        description="Material knowledge",
        order=0,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


def _auth_headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def test_regular_user_cannot_create_editorial_guide(
    auth_client,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)

    response = await auth_client.post(
        "/api/v1/wiki/author/articles",
        json={
            "category_id": category.id,
            "space_key": "guides",
            "language": "ru",
            "title": "From shelf to printer",
            "summary": "A product guide",
            "content": "Guide body",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_WIKI_GUIDES_EDITOR_ONLY"


async def test_legacy_admin_create_also_records_published_revision(
    admin_client,
    db_session,
):
    category = await _seed_wiki(db_session)

    response = await admin_client.post(
        "/api/v1/wiki/articles",
        json={
            "category_id": category.id,
            "title": "Legacy editor article",
            "slug": "legacy-editor-article",
            "summary": "Summary",
            "content": "Body",
            "published": True,
        },
    )

    assert response.status_code == 200, response.text
    history = await admin_client.get(
        "/api/v1/wiki/articles/legacy-editor-article/history"
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["authorship"] == "editorial"


async def test_public_article_list_never_exposes_private_drafts(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=_auth_headers(auth_user),
        json={
            "category_id": category.id,
            "title": "Private draft title",
            "summary": "Private draft summary",
            "content": "Private draft body",
        },
    )
    assert created.status_code == 201, created.text

    anonymous = await client.get("/api/v1/wiki/articles?published_only=false")
    assert anonymous.status_code == 403
    assert anonymous.json()["detail"]["code"] == "ERR_ACCESS_DENIED"

    member = await client.get(
        "/api/v1/wiki/articles?published_only=false",
        headers=_auth_headers(auth_user),
    )
    assert member.status_code == 403

    editor = await client.get(
        "/api/v1/wiki/articles?published_only=false",
        headers=_auth_headers(admin_user),
    )
    assert editor.status_code == 200


async def test_public_history_excludes_moderation_and_peer_review_data(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    article = await client.post(
        "/api/v1/wiki/author/articles",
        headers=_auth_headers(admin_user),
        json={
            "category_id": category.id,
            "title": "Public history",
            "slug": "public-history",
            "summary": "Published summary",
            "content": "Published body",
            "publish": True,
        },
    )
    revision = await client.post(
        f"/api/v1/wiki/author/articles/{article.json()['article_id']}/revisions",
        headers=_auth_headers(auth_user),
        json={"content": "Reviewed correction", "edit_summary": "Correct a fact"},
    )
    revision_id = revision.json()["id"]
    await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=_auth_headers(auth_user),
        json={},
    )
    await client.post(
        f"/api/v1/wiki/revisions/{revision_id}/reviews",
        headers=_auth_headers(admin_user),
        json={
            "verdict": "support",
            "comment": "Internal peer note",
            "evidence_url": "https://example.test/evidence",
        },
    )
    decision = await client.post(
        f"/api/v1/wiki/moderation/revisions/{revision_id}/decision",
        headers=_auth_headers(admin_user),
        json={"decision": "publish", "review_note": "Internal editor note"},
    )
    assert decision.status_code == 200, decision.text

    history = await client.get("/api/v1/wiki/articles/public-history/history")
    assert history.status_code == 200, history.text
    item = history.json()["items"][0]
    assert item["content"] == "Reviewed correction"
    for private_field in (
        "review_note",
        "reviewed_by_id",
        "reviewed_by_username",
        "peer_reviews",
        "base_content",
    ):
        assert private_field not in item


async def test_proposed_revision_does_not_replace_public_content_before_approval(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    admin_headers = _auth_headers(admin_user)
    user_headers = _auth_headers(auth_user)

    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=admin_headers,
        json={
            "category_id": category.id,
            "space_key": "knowledge",
            "language": "ru",
            "title": "PLA basics",
            "slug": "pla-basics",
            "summary": "Published summary",
            "content": "Published body",
            "publish": True,
        },
    )
    assert created.status_code == 201, created.text
    article_id = created.json()["article_id"]

    draft = await client.post(
        f"/api/v1/wiki/author/articles/{article_id}/revisions",
        headers=user_headers,
        json={"content": "Community correction", "edit_summary": "Fix a fact"},
    )
    assert draft.status_code == 201, draft.text
    revision_id = draft.json()["id"]

    submitted = await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=user_headers,
        json={},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == WikiRevisionStatus.PENDING_REVIEW.value

    before = await client.get("/api/v1/wiki/articles/pla-basics")
    assert before.status_code == 200, before.text
    assert before.json()["content"] == "Published body"

    decision = await client.post(
        f"/api/v1/wiki/moderation/revisions/{revision_id}/decision",
        headers=admin_headers,
        json={"decision": "publish", "review_note": "Verified"},
    )
    assert decision.status_code == 200, decision.text

    after = await client.get("/api/v1/wiki/articles/pla-basics")
    assert after.status_code == 200, after.text
    assert after.json()["content"] == "Community correction"

    history = await client.get("/api/v1/wiki/articles/pla-basics/history")
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 2


async def test_stale_revision_cannot_overwrite_newer_published_revision(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    admin_headers = _auth_headers(admin_user)
    author_headers = _auth_headers(auth_user)
    article = await client.post(
        "/api/v1/wiki/author/articles",
        headers=admin_headers,
        json={
            "category_id": category.id,
            "title": "Concurrent article",
            "summary": "Version one",
            "content": "Version one body",
            "publish": True,
        },
    )
    article_id = article.json()["article_id"]

    first = await client.post(
        f"/api/v1/wiki/author/articles/{article_id}/revisions",
        headers=author_headers,
        json={"content": "Community version two", "edit_summary": "First branch"},
    )
    second = await client.post(
        f"/api/v1/wiki/author/articles/{article_id}/revisions",
        headers=admin_headers,
        json={"content": "Editorial stale branch", "edit_summary": "Second branch"},
    )
    for revision, headers in ((first, author_headers), (second, admin_headers)):
        submitted = await client.post(
            f"/api/v1/wiki/author/revisions/{revision.json()['id']}/submit",
            headers=headers,
            json={},
        )
        assert submitted.status_code == 200, submitted.text

    published = await client.post(
        f"/api/v1/wiki/moderation/revisions/{first.json()['id']}/decision",
        headers=admin_headers,
        json={"decision": "publish"},
    )
    assert published.status_code == 200, published.text

    stale = await client.post(
        f"/api/v1/wiki/moderation/revisions/{second.json()['id']}/decision",
        headers=admin_headers,
        json={"decision": "publish"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "ERR_WIKI_STALE_REVISION"

    live = await client.get(f"/api/v1/wiki/articles/{article.json()['article_slug']}")
    assert live.status_code == 200
    assert live.json()["content"] == "Community version two"


async def test_community_author_cannot_publish_own_submission_after_role_change(
    client,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    headers = _auth_headers(auth_user)

    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=headers,
        json={
            "category_id": category.id,
            "space_key": "knowledge",
            "language": "ru",
            "title": "Community article",
            "summary": "Community summary",
            "content": "Community body",
        },
    )
    assert created.status_code == 201, created.text
    revision_id = created.json()["id"]
    assert created.json()["article_provenance"] == WikiArticleProvenance.COMMUNITY.value

    submitted = await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=headers,
        json={},
    )
    assert submitted.status_code == 200, submitted.text

    auth_user.role = UserRole.MODERATOR
    await db_session.commit()

    decision = await client.post(
        f"/api/v1/wiki/moderation/revisions/{revision_id}/decision",
        headers=headers,
        json={"decision": "publish"},
    )
    assert decision.status_code == 403
    assert decision.json()["detail"]["code"] == "ERR_WIKI_SELF_REVIEW_FORBIDDEN"

    article = (
        await db_session.execute(
            select(WikiArticle).where(WikiArticle.id == created.json()["article_id"])
        )
    ).scalar_one()
    assert article.published is False
    assert article.published_revision_id is None


async def test_author_has_only_one_active_revision_per_article(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=_auth_headers(admin_user),
        json={
            "category_id": category.id,
            "title": "PETG basics",
            "summary": "Published summary",
            "content": "Published body",
            "publish": True,
        },
    )
    article_id = created.json()["article_id"]

    first = await client.post(
        f"/api/v1/wiki/author/articles/{article_id}/revisions",
        headers=_auth_headers(auth_user),
        json={"summary": "First change"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/wiki/author/articles/{article_id}/revisions",
        headers=_auth_headers(auth_user),
        json={"summary": "Second change"},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ERR_WIKI_ACTIVE_REVISION_EXISTS"


async def test_peer_review_queue_excludes_own_and_already_reviewed_revisions(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    author_headers = _auth_headers(auth_user)
    reviewer_headers = _auth_headers(admin_user)
    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=author_headers,
        json={
            "category_id": category.id,
            "space_key": "knowledge",
            "language": "ru",
            "title": "Reviewable article",
            "summary": "Community summary",
            "content": "Community body",
        },
    )
    revision_id = created.json()["id"]
    await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=author_headers,
        json={},
    )

    own_queue = await client.get(
        "/api/v1/wiki/revisions/reviewable", headers=author_headers
    )
    assert own_queue.status_code == 200
    assert own_queue.json()["total"] == 0

    review_queue = await client.get(
        "/api/v1/wiki/revisions/reviewable", headers=reviewer_headers
    )
    assert review_queue.status_code == 200
    assert [item["id"] for item in review_queue.json()["items"]] == [revision_id]

    reviewed = await client.post(
        f"/api/v1/wiki/revisions/{revision_id}/reviews",
        headers=reviewer_headers,
        json={"verdict": "support", "comment": "Verified"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["peer_reviews"][0]["verdict"] == "support"

    after = await client.get(
        "/api/v1/wiki/revisions/reviewable", headers=reviewer_headers
    )
    assert after.status_code == 200
    assert after.json()["total"] == 0


async def test_rejected_revision_is_preserved_and_retried_as_new_draft(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    admin_headers = _auth_headers(admin_user)
    author_headers = _auth_headers(auth_user)
    article = await client.post(
        "/api/v1/wiki/author/articles",
        headers=admin_headers,
        json={
            "category_id": category.id,
            "title": "Retry article",
            "summary": "Published summary",
            "content": "Published body",
            "publish": True,
        },
    )
    draft = await client.post(
        f"/api/v1/wiki/author/articles/{article.json()['article_id']}/revisions",
        headers=author_headers,
        json={"content": "Incorrect correction", "edit_summary": "First attempt"},
    )
    revision_id = draft.json()["id"]
    await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=author_headers,
        json={},
    )
    rejected = await client.post(
        f"/api/v1/wiki/moderation/revisions/{revision_id}/decision",
        headers=admin_headers,
        json={"decision": "reject", "review_note": "Verify the temperature"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    retried = await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/retry",
        headers=author_headers,
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "draft"
    assert retried.json()["revision_number"] == 3
    assert retried.json()["content"] == "Incorrect correction"
    assert retried.json()["review_note"] is None

    old_revision = await client.get(
        f"/api/v1/wiki/author/revisions/{revision_id}",
        headers=author_headers,
    )
    assert old_revision.json()["status"] == "rejected"
    assert old_revision.json()["review_note"] == "Verify the temperature"


async def test_markdown_sync_versions_changes_but_not_identical_content(
    auth_user,
    db_session,
):
    await _seed_wiki(db_session)
    metadata = {
        "title": "Synchronized article",
        "summary": "A focused **summary** for cards.",
        "slug": "synchronized-article",
        "category": "materials",
        "status": "published",
        "author_id": auth_user.id,
    }
    file_path = Path("synchronized-article.md")

    first = await sync_article(db_session, file_path, "First body", metadata)
    second = await sync_article(db_session, file_path, "First body", metadata)
    third = await sync_article(db_session, file_path, "Corrected body", metadata)

    assert first["status"] == "created"
    assert second["status"] == "unchanged"
    assert third["status"] == "updated"
    revision_count = (
        await db_session.execute(select(func.count(WikiRevision.id)))
    ).scalar_one()
    assert revision_count == 2
    article = (
        await db_session.execute(
            select(WikiArticle).where(WikiArticle.slug == "synchronized-article")
        )
    ).scalar_one()
    assert article.content == "Corrected body"
    assert article.summary == "A focused summary for cards."


async def test_markdown_sync_respects_space_and_language_metadata(
    auth_user,
    db_session,
):
    await _seed_wiki(db_session)
    result = await sync_article(
        db_session,
        Path("first-steps.md"),
        "Official product guidance",
        {
            "title": "First steps",
            "slug": "first-steps",
            "category": "beginners",
            "status": "published",
            "space": "guides",
            "language": "en",
            "author_id": auth_user.id,
        },
    )

    assert result["status"] == "created"
    article = (
        await db_session.execute(
            select(WikiArticle).where(WikiArticle.slug == "first-steps")
        )
    ).scalar_one()
    assert article.space_id == 1
    assert article.language == "en"


async def test_markdown_sync_does_not_replace_article_of_another_language(
    auth_user,
    db_session,
):
    await _seed_wiki(db_session)
    russian = await sync_article(
        db_session,
        Path("first-steps-ru.md"),
        "Русский текст",
        {
            "title": "Первые шаги",
            "slug": "first-steps-shared",
            "category": "materials",
            "status": "published",
            "language": "ru",
            "author_id": auth_user.id,
        },
    )
    english = await sync_article(
        db_session,
        Path("first-steps-en.md"),
        "English text",
        {
            "title": "First steps",
            "slug": "first-steps-shared",
            "category": "materials",
            "status": "published",
            "language": "en",
            "author_id": auth_user.id,
        },
    )

    assert russian["status"] == "created"
    assert english["status"] == "skipped"
    article = (
        await db_session.execute(
            select(WikiArticle).where(WikiArticle.slug == "first-steps-shared")
        )
    ).scalar_one()
    assert article.language == "ru"
    assert article.content == "Русский текст"


async def test_account_deletion_removes_private_wiki_work_and_anonymizes_published(
    client,
    admin_user,
    auth_user,
    db_session,
):
    category = await _seed_wiki(db_session)
    author_headers = _auth_headers(auth_user)
    admin_headers = _auth_headers(admin_user)

    private_article = await client.post(
        "/api/v1/wiki/author/articles",
        headers=author_headers,
        json={
            "category_id": category.id,
            "title": "Delete my private draft",
            "summary": "Private summary",
            "content": "Private content",
        },
    )
    public_article = await client.post(
        "/api/v1/wiki/author/articles",
        headers=author_headers,
        json={
            "category_id": category.id,
            "title": "Keep public knowledge",
            "slug": "keep-public-knowledge",
            "summary": "Public summary",
            "content": "Public content",
        },
    )
    public_revision_id = public_article.json()["id"]
    await client.post(
        f"/api/v1/wiki/author/revisions/{public_revision_id}/submit",
        headers=author_headers,
        json={},
    )
    approved = await client.post(
        f"/api/v1/wiki/moderation/revisions/{public_revision_id}/decision",
        headers=admin_headers,
        json={"decision": "publish"},
    )
    assert approved.status_code == 200, approved.text
    correction = await client.post(
        f"/api/v1/wiki/author/articles/{public_article.json()['article_id']}/revisions",
        headers=author_headers,
        json={"content": "Unpublished personal correction"},
    )
    assert correction.status_code == 201, correction.text

    await delete_user_account(
        auth_user,
        delete_reviews=True,
        release_brand_representation=False,
        db=db_session,
    )

    assert await db_session.get(WikiArticle, private_article.json()["article_id"]) is None
    preserved = await db_session.get(WikiArticle, public_article.json()["article_id"])
    assert preserved is not None
    assert preserved.author is None
    assert preserved.created_by_id is None
    assert await db_session.get(WikiRevision, correction.json()["id"]) is None
    published_revision = await db_session.get(WikiRevision, public_revision_id)
    assert published_revision is not None
    assert published_revision.created_by_id is None
