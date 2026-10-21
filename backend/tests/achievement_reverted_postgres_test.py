"""Reverted printer reports on migrated PostgreSQL, where ``meta`` is JSON, not JSONB.

Fixtures are retained. No schema changes or cleanup are performed.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.print_job import PrintJob, PrintJobEvent, PrintJobMaterial, PrintJobStatus
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.services.achievement_service import MATERIAL_TO_PRINT, achievement_overview
from tests.conftest import accepted_legal

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="requires FH_TEST_POSTGRES_URL pointing at migrated local dev",
    ),
]


async def test_reverted_printer_report_does_not_count_on_postgres():
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    try:
        async with sessions() as db:
            user = User(
                email=f"achievement-pg-{suffix}@example.com",
                username=f"achievement_pg_{suffix}",
                password_hash="unused",
                active=True,
                email_verified=True,
                **accepted_legal(),
            )
            db.add(user)
            await db.flush()
            calculation = CalculatorHistoryEntry(
                user_id=user.id,
                title="Production calculation",
                pricing_method="cost_plus",
                request_data={"quantity": 1},
                result_data={"total": 600},
                parsed_gcode={"print_time_seconds": 1800},
            )
            printer = UserPrinterDevice(user_id=user.id, name=f"Achievement printer {suffix}")
            spool = UserSpool(user_id=user.id, initial_weight_g=1000, used_weight_g=50)
            db.add_all([calculation, printer, spool])
            await db.flush()
            now = datetime.now(timezone.utc)
            job = PrintJob(
                user_id=user.id,
                physical_printer_id=printer.id,
                calculator_history_id=calculation.id,
                title="Linked production job",
                status=PrintJobStatus.completed,
                source="manual",
                source_ref=f"achievement-reverted-{suffix}",
                source_payload_hash="a" * 64,
                finished_at=now,
            )
            db.add(job)
            await db.flush()
            usage = PresetUsageEvent(
                user_id=user.id,
                device_id=printer.id,
                spool_id=spool.id,
                print_job_id=job.id,
                event_type=PresetUsageEventType.printer_report,
                delta_weight_g=50,
                remaining_weight_g=950,
                meta={"reverted": True},
            )
            db.add_all(
                [
                    PrintJobMaterial(
                        print_job_id=job.id,
                        spool_id=spool.id,
                        planned_weight_g=50,
                        spool_snapshot={"spool_name": "Achievement spool"},
                    ),
                    PrintJobEvent(
                        print_job_id=job.id,
                        user_id=user.id,
                        status=PrintJobStatus.completed,
                        source="octoprint",
                        event_key="octoprint:completed",
                        payload_hash="c" * 64,
                        occurred_at=now,
                    ),
                    usage,
                ]
            )
            await db.commit()

            taken_back = await achievement_overview(db, user_id=user.id)
            assert MATERIAL_TO_PRINT not in {item.code for item in taken_back.achievements}

            # No meta at all is the common case for an ordinary printer report.
            usage = await db.scalar(
                select(PresetUsageEvent).where(PresetUsageEvent.print_job_id == job.id)
            )
            usage.meta = None
            await db.commit()

            counted = await achievement_overview(db, user_id=user.id)
            assert MATERIAL_TO_PRINT in {item.code for item in counted.achievements}
    finally:
        await engine.dispose()
