from typing import Dict, Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.realtime import hub
from app.dependencies import get_interes_service, get_principal_opcional
from app.schemas.auth import Principal
from app.schemas.common import ObjectIdStr
from app.services.interes_service import InteresService

router = APIRouter(tags=["tiempo real"])


class InteresCreate(BaseModel):
    espacio_id: Optional[ObjectIdStr] = None
    # Para invitados sin sesión: un id aleatorio que la app genera y guarda.
    dispositivo_id: Optional[str] = Field(default=None, min_length=8, max_length=64)


class InteresRead(BaseModel):
    sede_id: str
    viendo: int
    por_espacio: Dict[str, int]


@router.post("/sedes/{sede_id}/interes", response_model=InteresRead)
async def marcar_interes(
    sede_id: str,
    data: InteresCreate,
    principal: Optional[Principal] = Depends(get_principal_opcional),
    service: InteresService = Depends(get_interes_service),
):
    """La app lo llama al abrir una sede y cada ~60 s mientras la tenga en pantalla (expira a los 2 min)."""
    clave = str(principal.id) if principal else f"dispositivo:{data.dispositivo_id or 'anonimo'}"
    return await service.marcar(sede_id, clave, data.espacio_id)


@router.get("/sedes/{sede_id}/interes", response_model=InteresRead)
async def consultar_interes(sede_id: str, service: InteresService = Depends(get_interes_service)):
    return await service.consultar(sede_id)


@router.websocket("/ws/sedes/{sede_id}")
async def eventos_sede(websocket: WebSocket, sede_id: str):
    """Eventos en vivo de la sede: check_in, check_out, espacio_estado, reserva_*, pago, interes.

    Cada mensaje trae `evento`, `espacio_id` y `estado_espacio` (si cambió una plaza), `descripcion` y `fecha`.
    """
    await hub.conectar(sede_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # mantiene la conexión; el cliente puede mandar pings
    except WebSocketDisconnect:
        hub.desconectar(sede_id, websocket)
