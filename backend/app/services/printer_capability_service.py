"""Capability projection shared by every authenticated printer adapter."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.printer_capabilities import normalize_capabilities
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.octoprint_bridge import OctoPrintBridgeConnection
from app.models.printer_bridge_credential import PrinterBridgeCredential


async def refresh_material_system_capabilities(
    db: AsyncSession,
    material_system_id: int,
) -> None:
    """Project normalized capabilities from active, authenticated connectors."""
    await db.flush()
    system = await db.get(MaterialSystem, material_system_id)
    if system is None:
        return
    has_bridge_credential = (
        select(PrinterBridgeCredential.id)
        .where(
            PrinterBridgeCredential.connector_id == PhysicalPrinterConnector.id,
            PrinterBridgeCredential.token_hash.is_not(None),
            PrinterBridgeCredential.revoked_at.is_(None),
        )
        .exists()
    )
    has_octoprint_credential = (
        select(OctoPrintBridgeConnection.id)
        .where(
            OctoPrintBridgeConnection.connector_id == PhysicalPrinterConnector.id,
            OctoPrintBridgeConnection.token_hash.is_not(None),
            OctoPrintBridgeConnection.revoked_at.is_(None),
        )
        .exists()
    )
    trusted_legacy_connector = or_(
        and_(
            PhysicalPrinterConnector.provider == "happy_hare",
            PhysicalPrinterConnector.transport.in_(
                ["orca_plugin_lan", "spoolman_compat", "legacy_adapter"]
            ),
        ),
        and_(
            PhysicalPrinterConnector.provider == "legacy",
            PhysicalPrinterConnector.transport.in_(["spoolman_compat", "legacy_adapter"]),
        ),
    )
    connector_rows = (
        await db.execute(
            select(
                PhysicalPrinterConnector.provider,
                PhysicalPrinterConnector.transport,
                PhysicalPrinterConnector.capabilities,
            ).where(
                PhysicalPrinterConnector.material_system_id == material_system_id,
                PhysicalPrinterConnector.active.is_(True),
                or_(has_bridge_credential, has_octoprint_credential, trusted_legacy_connector),
            )
        )
    ).all()
    system.capabilities = sorted(
        {
            capability
            for provider, transport, capabilities in connector_rows
            for capability in normalize_capabilities(
                capabilities or [], provider=provider, transport=transport
            )
        }
    )
