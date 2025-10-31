"""Spoolman integration endpoints (stub for MVP)."""

from fastapi import APIRouter

from pydantic import BaseModel

router = APIRouter(prefix="/spoolman", tags=["spoolman"])


class SpoolmanSyncResponse(BaseModel):
    """Schema for Spoolman sync response."""

    status: str
    message: str


@router.get("/sync", response_model=SpoolmanSyncResponse)
async def sync_spoolman() -> SpoolmanSyncResponse:
    """
    Синхронизация со Spoolman (заглушка для MVP).
    
    **Будет реализовано в Фазе 5.**
    
    Планируемая функциональность:
    - Импорт катушек из Spoolman
    - Экспорт в Spoolman
    - Двусторонняя синхронизация остатков материала
    - Real-time updates через WebSocket
    """
    return SpoolmanSyncResponse(
        status="TODO",
        message="Spoolman integration will be implemented in Phase 5. For now, use direct FilamentHub API.",
    )
