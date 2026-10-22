"""Admin-only proposal editing and explicitly confirmed catalog application."""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.api.v1.endpoints.catalog_master_import import _raise_service_error
from app.core.dependencies import get_current_admin_user, require_catalog_curation_service_account
from app.core.errors import (
    ERR_CATALOG_CURATION_INVALID,
    ERR_CATALOG_CURATION_NO_QUOTES,
    ERR_CATALOG_CURATION_NOT_FOUND,
    ERR_CATALOG_CURATION_SERVICE_ACCOUNT_NOT_FOUND,
    ERR_CATALOG_CURATION_STALE,
    raise_error,
)
from app.db.session import get_db
from app.models import (
    CatalogCurationProposal,
    CatalogCurationServiceAccount,
    CatalogImageConfirmation,
    Filament,
    User,
)
from app.schemas.catalog_curation import (
    CatalogCurationApply,
    CatalogCurationCreate,
    CatalogCurationDetail,
    CatalogCurationList,
    CatalogCurationListItem,
    CatalogCurationPatch,
    CatalogCurationPreview,
    CatalogCurationRevision,
    CatalogCurationServiceAccountCreate,
    CatalogCurationServiceAccountCreated,
    CatalogCurationServiceAccountList,
    CatalogCurationServiceAccountSummary,
    CatalogCurationSummary,
    CatalogQuoteCheckItem,
    CatalogQuoteCheckReport,
    CatalogQuoteCheckSummary,
    CatalogQuoteImageConfirmation,
    CatalogSourceFactReview,
)
from app.schemas.catalog_import import CatalogImportApplyResponse
from app.services.catalog_curation_service import (
    build_curation_plan,
    proposal_digest,
    validate_proposal,
)
from app.services.catalog_master_import_service import (
    CatalogMasterImportError,
    _public_rows,
    apply_plan,
    issue_confirmation,
    plan_digest,
    summarize,
    verify_confirmation,
)
from app.services.catalog_quote_claims import (
    VERIFIED,
    claim_states,
    gated_source_facts,
    job_pending,
    load_checks,
    load_confirmations,
    proposal_claims,
    quote_gate,
    summarize_states,
)
from app.services.catalog_quote_queue import enqueue_if_quotable, enqueue_quote_check

router = APIRouter(prefix="/admin/catalog/curation/proposals", tags=["admin", "catalog"])
service_account_router = APIRouter(
    prefix="/admin/catalog/curation/service-accounts", tags=["admin", "catalog"]
)
service_router = APIRouter(
    prefix="/service/catalog/curation/proposals", tags=["catalog-curation-service"]
)
Admin = Annotated[User, Depends(get_current_admin_user)]
Database = Annotated[AsyncSession, Depends(get_db)]
ServiceAccount = Annotated[
    CatalogCurationServiceAccount, Depends(require_catalog_curation_service_account)
]


async def _proposal(db: AsyncSession, proposal_id: int, *, lock: bool = False):
    statement = select(CatalogCurationProposal).where(CatalogCurationProposal.id == proposal_id)
    if lock:
        statement = statement.with_for_update()
    proposal = await db.scalar(statement.execution_options(populate_existing=True))
    if proposal is None:
        raise_error(404, ERR_CATALOG_CURATION_NOT_FOUND)
    return proposal


def _require_revision(proposal: CatalogCurationProposal, revision: int) -> None:
    if proposal.status != "draft" or proposal.revision != revision:
        raise_error(409, ERR_CATALOG_CURATION_STALE)


def _validate(data: CatalogCurationCreate) -> None:
    try:
        validate_proposal(data)
    except CatalogMasterImportError as exc:
        raise_error(422, ERR_CATALOG_CURATION_INVALID, params={"message": exc.message})


@router.post("", response_model=CatalogCurationDetail, status_code=201)
async def create_proposal(data: CatalogCurationCreate, admin: Admin, db: Database):
    _validate(data)
    proposal = CatalogCurationProposal(
        **data.model_dump(mode="json"),
        created_by_user_id=admin.id,
        updated_by_user_id=admin.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _list_proposals(db: AsyncSession, offset: int, size: int, *filters) -> CatalogCurationList:
    total = await db.scalar(
        select(func.count()).select_from(CatalogCurationProposal).where(*filters)
    )
    draft = CatalogCurationProposal.draft
    # Counted in SQL so the page never loads whole drafts.
    rows = (
        await db.execute(
            select(
                CatalogCurationProposal,
                draft["brands"][0]["name"].as_string(),
                func.json_array_length(draft["filaments"]),
                CatalogCurationServiceAccount.name,
            )
            .options(
                load_only(
                    *[
                        getattr(CatalogCurationProposal, field)
                        for field in CatalogCurationSummary.model_fields
                    ]
                )
            )
            .outerjoin(
                CatalogCurationServiceAccount,
                CatalogCurationServiceAccount.id
                == CatalogCurationProposal.created_by_service_account_id,
            )
            .where(*filters)
            .order_by(CatalogCurationProposal.id.desc())
            .offset(offset)
            .limit(size)
        )
    ).all()
    return CatalogCurationList(
        total=total or 0,
        items=[
            CatalogCurationListItem.model_validate(
                {
                    **CatalogCurationSummary.model_validate(proposal).model_dump(),
                    "brand_name": brand_name,
                    "filament_count": filament_count or 0,
                    "author_name": author_name,
                }
            )
            for proposal, brand_name, filament_count, author_name in rows
        ],
    )


@router.get("", response_model=CatalogCurationList)
async def list_proposals(
    admin: Admin, db: Database, offset: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100)
):
    return await _list_proposals(db, offset, size)


@router.get("/{proposal_id}", response_model=CatalogCurationDetail)
async def get_proposal(proposal_id: int, admin: Admin, db: Database):
    return await _proposal(db, proposal_id)


@router.patch("/{proposal_id}", response_model=CatalogCurationDetail)
async def patch_proposal(
    proposal_id: int, request: CatalogCurationPatch, admin: Admin, db: Database
):
    proposal = await _proposal(db, proposal_id)
    _require_revision(proposal, request.revision)
    changes = request.model_dump(mode="json", exclude_unset=True, exclude={"revision"})
    if any(value is None for value in changes.values()):
        raise_error(422, ERR_CATALOG_CURATION_INVALID)
    data = CatalogCurationCreate.model_validate(
        {
            **{field: getattr(proposal, field) for field in CatalogCurationCreate.model_fields},
            **changes,
        }
    )
    _validate(data)
    result = await db.execute(
        update(CatalogCurationProposal)
        .where(
            CatalogCurationProposal.id == proposal_id,
            CatalogCurationProposal.revision == request.revision,
            CatalogCurationProposal.status == "draft",
        )
        .values(
            **changes,
            revision=request.revision + 1,
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=admin.id,
            updated_by_service_account_id=None,
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        raise_error(409, ERR_CATALOG_CURATION_STALE)
    await db.commit()
    return await _proposal(db, proposal_id)


@router.post("/{proposal_id}/preview", response_model=CatalogCurationPreview)
async def preview_proposal(
    proposal_id: int, request: CatalogCurationRevision, admin: Admin, db: Database
):
    proposal = await _proposal(db, proposal_id)
    _require_revision(proposal, request.revision)
    gate = await quote_gate(db, proposal)
    draft, plan = await build_curation_plan(db, proposal, admin_user_id=admin.id, gate=gate)
    summary = summarize(plan)
    facts_by_key: dict[str, list[dict]] = {}
    for fact in gated_source_facts(getattr(proposal, "source_facts", []) or [], gate):
        facts_by_key.setdefault(fact["filament_key"], []).append(fact)
    source_facts_review = []
    for row in proposal.draft.get("filaments", []):
        key = str(row.get("filament_key") or "").strip()
        if row.get("mode") not in {"create", "update"} or row.get("enabled", True) is False:
            continue
        facts = facts_by_key.get(key, [])
        mapped = sum(fact["disposition"] == "mapped" for fact in facts)
        unsupported = sum(fact["disposition"] == "unsupported" for fact in facts)
        unresolved = sum(fact["disposition"] == "unresolved" for fact in facts)
        total = len(facts)
        captured = mapped + unsupported
        coverage_percent = (captured * 100 // total) if total else 0
        source_facts_review.append(
            CatalogSourceFactReview(
                filament_key=key,
                total=total,
                mapped=mapped,
                unsupported=unsupported,
                unresolved=unresolved,
                captured=captured,
                coverage_percent=coverage_percent,
            )
        )
    token, expires = None, None
    if summary["error"] == 0:
        token, expires = issue_confirmation(
            user_id=admin.id,
            draft_hash=proposal_digest(proposal),
            calculated_plan_digest=plan_digest(plan),
        )
    return CatalogCurationPreview(
        proposal_id=proposal.id,
        revision=proposal.revision,
        draft=draft,
        rows=_public_rows(plan),
        summary=summary,
        unmapped_facts=proposal.unmapped_facts,
        source_facts=getattr(proposal, "source_facts", []) or [],
        source_facts_review=source_facts_review,
        confirmation_token=token,
        confirmation_expires_at=expires,
    )


async def _quote_report(
    db: AsyncSession, proposal: CatalogCurationProposal, claims: list | None = None
) -> CatalogQuoteCheckReport:
    if claims is None:
        claims = await proposal_claims(db, proposal)
    states = claim_states(
        claims, await load_checks(db, proposal.id), await load_confirmations(db, proposal.id)
    )
    return CatalogQuoteCheckReport(
        items=[
            CatalogQuoteCheckItem(
                scope=state.claim.scope,
                sheet=state.claim.sheet,
                key=state.claim.key,
                field=state.claim.field,
                status=state.status,
                reason=state.reason,
                url=state.url,
                checked_at=state.checked_at,
                confirmed=state.confirmed,
                gating=state.claim.gating,
            )
            for state in states
            if state.status != VERIFIED
        ],
        summary=CatalogQuoteCheckSummary(**summarize_states(states)),
        job_pending=await job_pending(db, proposal.id),
    )


@router.get("/{proposal_id}/quote-checks", response_model=CatalogQuoteCheckReport)
async def get_quote_checks(proposal_id: int, admin: Admin, db: Database):
    return await _quote_report(db, await _proposal(db, proposal_id))


@router.post(
    "/{proposal_id}/verify-sources", response_model=CatalogQuoteCheckReport, status_code=202
)
async def verify_sources(proposal_id: int, admin: Admin, db: Database):
    """Queue a server-side check of every quote; repeating the request coalesces."""
    proposal = await _proposal(db, proposal_id)
    if not await proposal_claims(db, proposal):
        raise_error(422, ERR_CATALOG_CURATION_NO_QUOTES)
    await enqueue_quote_check(db, proposal_id)
    await db.commit()
    return await _quote_report(db, await _proposal(db, proposal_id))


@router.post(
    "/{proposal_id}/quote-checks/image-confirmation", response_model=CatalogQuoteCheckReport
)
async def confirm_image_claim(
    proposal_id: int, request: CatalogQuoteImageConfirmation, admin: Admin, db: Database
):
    """Record (or withdraw) an administrator's "checked by eye" for one image claim."""
    proposal = await _proposal(db, proposal_id, lock=True)
    if proposal.status != "draft":
        raise_error(409, ERR_CATALOG_CURATION_STALE)
    identity = (request.scope, request.sheet, request.key, request.field)
    claims = await proposal_claims(db, proposal)
    claim = next((item for item in claims if item.identity == identity), None)
    if claim is None:
        raise_error(422, ERR_CATALOG_CURATION_INVALID)
    state = claim_states([claim], await load_checks(db, proposal_id))[0]
    if state.status != "image_only":
        raise_error(422, ERR_CATALOG_CURATION_INVALID)
    confirmations = await load_confirmations(db, proposal_id)
    existing = confirmations.get(identity)
    if request.confirmed:
        if existing is None:
            existing = CatalogImageConfirmation(
                proposal_id=proposal_id,
                scope=request.scope,
                sheet=request.sheet,
                key=request.key,
                field=request.field,
            )
            db.add(existing)
        existing.claim_hash = claim.claim_hash
        existing.confirmed_by_user_id = admin.id
        existing.confirmed_at = datetime.now(timezone.utc)
    elif existing is not None:
        await db.delete(existing)
    await db.commit()
    return await _quote_report(db, await _proposal(db, proposal_id), claims)


@router.post("/{proposal_id}/apply", response_model=CatalogImportApplyResponse)
async def apply_proposal(
    proposal_id: int, request: CatalogCurationApply, admin: Admin, db: Database
):
    try:
        proposal = await _proposal(db, proposal_id, lock=True)
        _require_revision(proposal, request.revision)
        draft, plan = await build_curation_plan(db, proposal, admin_user_id=admin.id)
        verify_confirmation(
            token=request.confirmation_token,
            user_id=admin.id,
            draft_hash=proposal_digest(proposal),
            calculated_plan_digest=plan_digest(plan),
        )
        batch = await apply_plan(db, draft, plan, admin_user_id=admin.id, curation=True)
        applied_filaments = {
            row.get("key"): row.get("target_id")
            for row in batch.plan_snapshot.get("rows", [])
            if row.get("sheet") == "Filaments"
            and row.get("status") not in {"error", "skipped"}
            and row.get("target_id") is not None
        }
        for fact in proposal.unmapped_facts or []:
            action = fact.get("public_action", "none")
            if action == "none":
                continue
            target_id = applied_filaments.get(fact.get("filament_key"))
            if target_id is None:
                # Disabled/skipped materials must never receive public facts.
                continue
            filament = await db.get(Filament, target_id)
            if filament is None:
                raise CatalogMasterImportError(
                    "ERR_CATALOG_IMPORT_STALE", "Filament disappeared"
                )
            properties = list(filament.additional_properties or [])
            property_key = str(fact["property_name"]).strip().casefold()
            kept = [
                item
                for item in properties
                if str(item.get("property_name", "")).strip().casefold() != property_key
            ]
            if action == "publish":
                kept.append(
                    {
                        "property_name": fact["property_name"],
                        "value_summary": fact["value_summary"],
                        "source_urls": [str(url) for url in fact["source_urls"]],
                        "kind": fact["kind"],
                    }
                )
            filament.additional_properties = kept
        batch.plan_snapshot = {
            **batch.plan_snapshot,
            "curation": {
                "proposal_id": proposal.id,
                "revision": proposal.revision,
                "title": proposal.title,
                "draft": proposal.draft,
                "evidence": proposal.evidence,
                "unmapped_facts": proposal.unmapped_facts,
                "source_facts": getattr(proposal, "source_facts", []) or [],
                "coverage_note": proposal.coverage_note,
            },
        }
        proposal.status = "applied"
        proposal.applied_batch_id = batch.id
        proposal.updated_at = datetime.now(timezone.utc)
        proposal.updated_by_user_id = admin.id
        await db.commit()
        return CatalogImportApplyResponse(batch_id=batch.id, summary=batch.summary)
    except CatalogMasterImportError as exc:
        await db.rollback()
        _raise_service_error(exc)
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        raise_error(409, ERR_CATALOG_CURATION_STALE)


@service_account_router.post("", response_model=CatalogCurationServiceAccountCreated, status_code=201)
async def create_service_account(
    request: CatalogCurationServiceAccountCreate, admin: Admin, db: Database
):
    """Issue one revocable draft-only key and reveal it only in this response."""
    token = "fhca_" + secrets.token_urlsafe(32)
    account = CatalogCurationServiceAccount(
        name=request.name,
        key_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        created_by_user_id=admin.id,
        expires_at=request.expires_at,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return CatalogCurationServiceAccountCreated(account=account, token=token)


@service_account_router.get("", response_model=CatalogCurationServiceAccountList)
async def list_service_accounts(
    admin: Admin,
    db: Database,
    offset: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
):
    total = await db.scalar(select(func.count()).select_from(CatalogCurationServiceAccount))
    accounts = (
        await db.scalars(
            select(CatalogCurationServiceAccount)
            .order_by(CatalogCurationServiceAccount.id.desc())
            .offset(offset)
            .limit(size)
        )
    ).all()
    return CatalogCurationServiceAccountList(
        total=total or 0,
        items=[CatalogCurationServiceAccountSummary.model_validate(item) for item in accounts],
    )


@service_account_router.post(
    "/{account_id}/revoke", response_model=CatalogCurationServiceAccountSummary
)
async def revoke_service_account(account_id: int, admin: Admin, db: Database):
    account = await db.scalar(
        select(CatalogCurationServiceAccount)
        .where(CatalogCurationServiceAccount.id == account_id)
        .with_for_update()
    )
    if account is None:
        raise_error(404, ERR_CATALOG_CURATION_SERVICE_ACCOUNT_NOT_FOUND)
    if account.revoked_at is None:
        account.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(account)
    return account


async def _service_proposal(
    db: AsyncSession, proposal_id: int, account_id: int, *, lock: bool = False
):
    statement = select(CatalogCurationProposal).where(
        CatalogCurationProposal.id == proposal_id,
        CatalogCurationProposal.created_by_service_account_id == account_id,
    )
    if lock:
        statement = statement.with_for_update()
    proposal = await db.scalar(statement.execution_options(populate_existing=True))
    if proposal is None:
        raise_error(404, ERR_CATALOG_CURATION_NOT_FOUND)
    return proposal


@service_router.post("", response_model=CatalogCurationDetail, status_code=201)
async def service_create_proposal(
    data: CatalogCurationCreate, account: ServiceAccount, db: Database
):
    _validate(data)
    proposal = CatalogCurationProposal(
        **data.model_dump(mode="json"),
        created_by_service_account_id=account.id,
        updated_by_service_account_id=account.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    await enqueue_if_quotable(db, proposal)
    return proposal


@service_router.get("", response_model=CatalogCurationList)
async def service_list_proposals(
    account: ServiceAccount,
    db: Database,
    offset: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
):
    return await _list_proposals(
        db, offset, size, CatalogCurationProposal.created_by_service_account_id == account.id
    )


@service_router.get("/{proposal_id}", response_model=CatalogCurationDetail)
async def service_get_proposal(
    proposal_id: int, account: ServiceAccount, db: Database
):
    return await _service_proposal(db, proposal_id, account.id)


@service_router.patch("/{proposal_id}", response_model=CatalogCurationDetail)
async def service_patch_proposal(
    proposal_id: int,
    request: CatalogCurationPatch,
    account: ServiceAccount,
    db: Database,
):
    proposal = await _service_proposal(db, proposal_id, account.id)
    _require_revision(proposal, request.revision)
    changes = request.model_dump(mode="json", exclude_unset=True, exclude={"revision"})
    if any(value is None for value in changes.values()):
        raise_error(422, ERR_CATALOG_CURATION_INVALID)
    data = CatalogCurationCreate.model_validate(
        {
            **{field: getattr(proposal, field) for field in CatalogCurationCreate.model_fields},
            **changes,
        }
    )
    _validate(data)
    result = await db.execute(
        update(CatalogCurationProposal)
        .where(
            CatalogCurationProposal.id == proposal_id,
            CatalogCurationProposal.created_by_service_account_id == account.id,
            CatalogCurationProposal.revision == request.revision,
            CatalogCurationProposal.status == "draft",
        )
        .values(
            **changes,
            revision=request.revision + 1,
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=None,
            updated_by_service_account_id=account.id,
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        raise_error(409, ERR_CATALOG_CURATION_STALE)
    await db.commit()
    proposal = await _service_proposal(db, proposal_id, account.id)
    await enqueue_if_quotable(db, proposal)
    return proposal
