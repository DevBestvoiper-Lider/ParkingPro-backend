from typing import List, Optional

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_usuario, get_suscripcion_service
from app.repositories.base import Document
from app.schemas.suscripcion import AlertaCreate, AlertaRead, PlanRead, SuscripcionCreate, SuscripcionRead
from app.services.suscripcion_service import SuscripcionService, planes

router = APIRouter(tags=["suscripciones"])


@router.get("/suscripciones/planes", response_model=List[PlanRead])
async def listar_planes():
    return planes()


@router.get("/suscripciones/mia", response_model=Optional[SuscripcionRead])
async def mi_suscripcion(
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    """La suscripción vigente, o null si el usuario está en el plan por uso."""
    return await service.vigente(usuario)


@router.post("/suscripciones", response_model=SuscripcionRead, status_code=status.HTTP_201_CREATED)
async def suscribirse(
    data: SuscripcionCreate,
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    return await service.suscribir(usuario, data)


@router.post("/suscripciones/mia/cancelar", response_model=SuscripcionRead)
async def cancelar_suscripcion(
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    """Deja de renovarse; los beneficios se mantienen hasta fecha_fin."""
    return await service.cancelar(usuario)


@router.get("/alertas", response_model=List[AlertaRead])
async def mis_alertas(
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    return await service.listar_alertas(usuario)


@router.post("/alertas", response_model=AlertaRead, status_code=status.HTTP_201_CREATED)
async def crear_alerta(
    data: AlertaCreate,
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    """Avisar cuando se libere un cupo en la sede (beneficio Afiliado)."""
    return await service.crear_alerta(usuario, data)


@router.delete("/alertas/{alerta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_alerta(
    alerta_id: str,
    usuario: Document = Depends(get_current_usuario),
    service: SuscripcionService = Depends(get_suscripcion_service),
):
    await service.eliminar_alerta(usuario, alerta_id)
