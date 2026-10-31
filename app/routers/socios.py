from typing import List

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_current_socio, get_liquidacion_service, get_parqueadero_service, get_socio_service
from app.repositories.base import Document
from app.schemas.liquidacion import CuentaRead, LiquidacionRead
from app.schemas.parqueadero import ParqueaderoNuevo, ParqueaderoRead
from app.schemas.socio import SocioRead
from app.services.liquidacion_service import LiquidacionService
from app.services.parqueadero_service import ParqueaderoService
from app.services.socio_service import SocioService

router = APIRouter(prefix="/socios", tags=["socios"])


@router.get("/me", response_model=SocioRead)
async def leer_socio_actual(socio: Document = Depends(get_current_socio)):
    return socio


@router.get("/me/parqueaderos", response_model=List[ParqueaderoRead])
async def portafolio(
    socio: Document = Depends(get_current_socio),
    service: SocioService = Depends(get_socio_service),
):
    """Sus parqueaderos. Para actuar en uno, el panel manda su id en `X-Parqueadero-Id`."""
    return await service.portafolio(socio)


@router.post("/me/parqueaderos", response_model=ParqueaderoRead, status_code=status.HTTP_201_CREATED)
async def agregar_parqueadero(
    data: ParqueaderoNuevo,
    socio: Document = Depends(get_current_socio),
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    return await service.agregar(socio, data)


@router.get("/me/cuenta", response_model=CuentaRead)
async def estado_de_cuenta(
    socio: Document = Depends(get_current_socio),
    service: LiquidacionService = Depends(get_liquidacion_service),
):
    """Lo que va de la semana más el saldo pendiente, y cuánto del límite de deuda está usando."""
    return await service.estado_de_cuenta(socio)


@router.get("/me/liquidaciones", response_model=List[LiquidacionRead])
async def liquidaciones(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    socio: Document = Depends(get_current_socio),
    service: LiquidacionService = Depends(get_liquidacion_service),
):
    return await service.listar(socio, skip, limit)
