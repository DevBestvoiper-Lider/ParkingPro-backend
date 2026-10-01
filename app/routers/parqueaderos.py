from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_current_admin, get_mapa_service, get_parqueadero_service
from app.models.enums import TipoEspacio
from app.repositories.base import Document
from app.schemas.parqueadero import (
    ParqueaderoCreate,
    ParqueaderoRead,
    ParqueaderoUpdate,
    SedeCercana,
    SedeCreate,
    SedeUpdate,
)
from app.services.mapa_service import MapaService
from app.services.parqueadero_service import ParqueaderoService

router = APIRouter(prefix="/parqueaderos", tags=["parqueaderos"])


@router.post("", response_model=ParqueaderoRead, status_code=status.HTTP_201_CREATED)
async def registrar_parqueadero(
    data: ParqueaderoCreate,
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    """Alta de un parqueadero junto con su primer administrador."""
    return await service.registrar(data)


@router.get("", response_model=List[ParqueaderoRead])
async def listar_parqueaderos(
    ciudad: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    return await service.listar(ciudad, skip, limit)


@router.get("/cercanos", response_model=List[SedeCercana])
async def listar_sedes_cercanas(
    latitud: float = Query(..., ge=-90, le=90),
    longitud: float = Query(..., ge=-180, le=180),
    radio_km: float = Query(5, gt=0, le=50),
    tipo: Optional[TipoEspacio] = None,
    q: Optional[str] = Query(None, description="Busca en nombre del parqueadero, sede o dirección"),
    service: MapaService = Depends(get_mapa_service),
):
    """Mapa GPS: sedes cercanas con precio desde y cupos libres en la próxima hora."""
    return await service.cercanos(latitud, longitud, radio_km, tipo, q)


@router.get("/{parqueadero_id}", response_model=ParqueaderoRead)
async def obtener_parqueadero(parqueadero_id: str, service: ParqueaderoService = Depends(get_parqueadero_service)):
    return await service.obtener(parqueadero_id)


@router.patch("/{parqueadero_id}", response_model=ParqueaderoRead)
async def actualizar_parqueadero(
    parqueadero_id: str,
    data: ParqueaderoUpdate,
    admin: Document = Depends(get_current_admin),
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    return await service.actualizar(parqueadero_id, data, admin)


@router.post("/{parqueadero_id}/sedes", response_model=ParqueaderoRead, status_code=status.HTTP_201_CREATED)
async def agregar_sede(
    parqueadero_id: str,
    data: SedeCreate,
    admin: Document = Depends(get_current_admin),
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    return await service.agregar_sede(parqueadero_id, data, admin)


@router.patch("/{parqueadero_id}/sedes/{sede_id}", response_model=ParqueaderoRead)
async def actualizar_sede(
    parqueadero_id: str,
    sede_id: str,
    data: SedeUpdate,
    admin: Document = Depends(get_current_admin),
    service: ParqueaderoService = Depends(get_parqueadero_service),
):
    return await service.actualizar_sede(parqueadero_id, sede_id, data, admin)
