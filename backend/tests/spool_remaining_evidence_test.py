"""How much the calculator may trust a spool's remaining weight."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.calculator import (
    CalculatorPreflightLineRequest,
    CalculatorPreflightRequest,
)
from app.services.calculator_preflight_service import calculate_material_preflight


async def _spool(db: AsyncSession) -> tuple[User, UserSpool]:
    user = User(
        email="remaining-evidence@example.com",
        username="remaining_evidence",
        password_hash="not-used",
        active=True,
    )
    spool = UserSpool(
        user=user, initial_weight_g=1000, used_weight_g=100, state=UserSpoolState.active
    )
    db.add_all([user, spool])
    await db.commit()
    return user, spool


def _event(user, spool, event_type, delta, **meta) -> PresetUsageEvent:
    return PresetUsageEvent(
        user_id=user.id,
        spool_id=spool.id,
        event_type=event_type,
        delta_weight_g=delta,
        remaining_weight_g=900,
        meta=meta or None,
    )


async def _evidence(db, user, spool):
    result = await calculate_material_preflight(
        db,
        user_id=user.id,
        payload=CalculatorPreflightRequest(
            lines=[
                CalculatorPreflightLineRequest(
                    line_id="line-1", weight_g=1, spool_ids=[spool.id]
                )
            ]
        ),
    )
    allocation = result.lines[0].allocations[0]
    return SimpleNamespace(
        evidence=allocation.remaining_evidence,
        confidence=allocation.remaining_confidence,
        status=allocation.remaining_status,
    )


@pytest.mark.asyncio
async def test_opening_balance_typed_at_creation_is_not_a_measurement(db_session):
    user, spool = await _spool(db_session)
    db_session.add(
        _event(user, spool, PresetUsageEventType.reconcile_adjust, 100, reason="opening_balance")
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence) == ("manual_update", "medium")


@pytest.mark.asyncio
async def test_a_real_weighing_is_high_confidence(db_session):
    user, spool = await _spool(db_session)
    db_session.add(_event(user, spool, PresetUsageEventType.reconcile_adjust, 5))
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence) == ("measurement", "high")


@pytest.mark.asyncio
async def test_estimates_and_reverted_reports_do_not_set_the_confidence(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.reconcile_adjust, 5),
            _event(user, spool, PresetUsageEventType.printer_report, 20, reverted=True),
            _event(user, spool, PresetUsageEventType.print_estimate, 30),
        ]
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence) == ("measurement", "high")


@pytest.mark.asyncio
async def test_estimated_printer_report_is_low_confidence(db_session):
    user, spool = await _spool(db_session)
    db_session.add(
        _event(
            user, spool, PresetUsageEventType.printer_report, 12, consumption_kind="estimated"
        )
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence, result.status) == (
        "provider_report",
        "low",
        "known",
    )


@pytest.mark.asyncio
async def test_a_report_waiting_for_reconciliation_makes_the_balance_unknown(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.reconcile_adjust, 5),
            _event(
                user,
                spool,
                PresetUsageEventType.printer_report,
                0,
                balance_accounting="needs_reconciliation",
            ),
        ]
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert result.status == "unknown"


@pytest.mark.asyncio
async def test_a_possibly_doubled_delta_stays_in_doubt_until_a_weighing(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.printer_report, 8, possible_repeat=True),
            _event(user, spool, PresetUsageEventType.printer_report, 4),
        ]
    )
    await db_session.commit()

    assert (await _evidence(db_session, user, spool)).status == "unknown"

    db_session.add(_event(user, spool, PresetUsageEventType.reconcile_adjust, 1))
    await db_session.commit()

    assert (await _evidence(db_session, user, spool)).status == "known"


@pytest.mark.asyncio
async def test_imported_spool_opening_balance_keeps_import_evidence(db_session):
    user, spool = await _spool(db_session)
    spool.source = "octoprint_spoolmanager"
    db_session.add(
        _event(user, spool, PresetUsageEventType.reconcile_adjust, 100, reason="opening_balance")
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence) == ("import", "medium")


@pytest.mark.asyncio
async def test_a_reverted_report_waiting_for_reconciliation_no_longer_blocks(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.reconcile_adjust, 5),
            _event(
                user,
                spool,
                PresetUsageEventType.printer_report,
                0,
                balance_accounting="needs_reconciliation",
                reverted=True,
            ),
        ]
    )
    await db_session.commit()

    assert (await _evidence(db_session, user, spool)).status == "known"


@pytest.mark.asyncio
async def test_a_prorated_report_is_low_confidence(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.reconcile_adjust, 5),
            _event(
                user,
                spool,
                PresetUsageEventType.printer_report,
                3,
                balance_accounting="prorated_after_balance",
            ),
        ]
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence, result.status) == (
        "provider_report",
        "low",
        "known",
    )


@pytest.mark.asyncio
async def test_history_before_the_latest_unreverted_weighing_is_not_needed(db_session):
    user, spool = await _spool(db_session)
    db_session.add_all(
        [
            _event(user, spool, PresetUsageEventType.printer_report, 8, possible_repeat=True),
            _event(user, spool, PresetUsageEventType.reconcile_adjust, 5),
            _event(
                user,
                spool,
                PresetUsageEventType.manual_adjust,
                -2,
                balance_observed_at="2026-01-01T00:00:00+00:00",
                reverted=True,
            ),
        ]
    )
    await db_session.commit()

    result = await _evidence(db_session, user, spool)

    assert (result.evidence, result.confidence, result.status) == (
        "measurement",
        "high",
        "known",
    )
