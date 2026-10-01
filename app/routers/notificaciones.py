from typing import List

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_current_usuario, get_notificacion_service
from app.repositories.base import Document
from app.schemas.suscripcion import NotificacionRead
from app.services.notificacion_service import NotificacionService

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("", response_model=List[NotificacionRead])
async def listar(
    no_leidas: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    usuario: Document = Depends(get_current_usuario),
    service: NotificacionService = Depends(get_notificacion_service),
):
    return await service.listar(usuario, no_leidas, skip, limit)


@router.post("/leer-todas", status_code=status.HTTP_204_NO_CONTENT)
async def leer_todas(
    usuario: Document = Depends(get_current_usuario),
    service: NotificacionService = Depends(get_notificacion_service),
):
    await service.marcar_todas_leidas(usuario)


@router.post("/{notificacion_id}/leer", response_model=NotificacionRead)
async def leer(
    notificacion_id: str,
    usuario: Document = Depends(get_current_usuario),
    service: NotificacionService = Depends(get_notificacion_service),
):
    return await service.marcar_leida(usuario, notificacion_id)
