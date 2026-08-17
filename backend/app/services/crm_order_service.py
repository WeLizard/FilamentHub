"""Creating a production order, from wherever it comes.

An order used to exist only as the consequence of an accepted quote, which made a
repeat job from a known customer impossible to book without first issuing a document
nobody asked for. The order is now created here, and both doors — accepting a quote and
booking one directly — go through the same function, so they cannot drift apart in what
they fill in.

What actually carries over is not the quote but the calculation beneath it: the totals
and the frozen material demand. An order booked with no calculation at all has nothing
to plan spool reservations from, and says so rather than pretending the demand is zero.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmOrder


def order_material_requirements(calculation_snapshot: dict | None) -> list[dict]:
    """Freeze the accepted preflight demand without creating reservations."""
    if not isinstance(calculation_snapshot, dict):
        return []
    preflight = calculation_snapshot.get("operational_preflight")
    if not isinstance(preflight, dict):
        return []
    request = preflight.get("request")
    result = preflight.get("result")
    if not isinstance(request, dict):
        return []
    result_lines = {
        line.get("line_id"): line
        for line in (result.get("lines", []) if isinstance(result, dict) else [])
        if isinstance(line, dict) and isinstance(line.get("line_id"), str)
    }
    requirements: list[dict] = []
    for line in request.get("lines", []):
        if not isinstance(line, dict) or not isinstance(line.get("line_id"), str):
            continue
        resolved = result_lines.get(line["line_id"], {})
        required_base = resolved.get("required_base_g", line.get("weight_g", 0))
        required_planned = resolved.get("required_planned_g", required_base)
        allocations = resolved.get("allocations", [])
        usable = [
            item
            for item in allocations
            if isinstance(item, dict)
            and isinstance(item.get("spool_id"), int)
            and float(item.get("planned_coverage_g") or 0) > 0
        ]
        requirements.append(
            {
                "line_id": line["line_id"],
                "label": line.get("label"),
                "filament_id": line.get("filament_id"),
                "required_base_g": max(0.0, float(required_base or 0)),
                "required_planned_g": max(0.0, float(required_planned or 0)),
                "suggested_spool_ids": [item["spool_id"] for item in usable][:16],
                "suggested_allocations": [
                    {
                        "spool_id": item["spool_id"],
                        "weight_g": float(item.get("planned_coverage_g") or 0),
                    }
                    for item in usable
                ][:16],
            }
        )
    return requirements


async def create_order(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
    currency: str,
    total: float,
    customer_id: int | None = None,
    quote_id: int | None = None,
    calculation_snapshot: dict | None = None,
) -> CrmOrder:
    """Book an order and give it its number.

    The number needs the row's own id, so the order is flushed before it is named. The
    caller owns the transaction and commits when the rest of its work is done.
    """
    now = datetime.now(timezone.utc)
    order = CrmOrder(
        user_id=user_id,
        quote_id=quote_id,
        customer_id=customer_id,
        # Replaced below; the column is unique and cannot wait for the id.
        number=f"pending-{uuid_mod.uuid4()}",
        title=title,
        currency=currency,
        total=total,
        material_requirements=order_material_requirements(calculation_snapshot),
    )
    db.add(order)
    await db.flush()
    order.number = f"ЗК-{now:%Y%m%d}-{order.id:05d}"
    return order
