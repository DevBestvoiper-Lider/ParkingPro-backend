from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_espacio_service, require_permiso
from app.models.enums import EstadoEspacio, TipoEspacio
from app.repositories.base import Document
from app.schemas.espacio import EspacioCreate, EspacioRead, EspacioUpdate, PlazaRead, ZonaRead
from app.services.espacio_service import EspacioService

router = APIRouter(prefix="/espacios", tags=["espacios"])


@router.get("", response_model=List[EspacioRead])
async def listar_espacios(
    sede_id: str,
    zona: Optional[str] = None,
    tipo: Optional[TipoEspacio] = None,
    estado: Optional[EstadoEspacio] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    service: EspacioService = Depends(get_espacio_service),
):
    return await service.listar(sede_id, zona, tipo, estado, skip, limit)


@router.get("/zonas", response_model=List[ZonaRead])
async def listar_zonas(sede_id: str, service: EspacioService = Depends(get_espacio_service)):
    return await service.zonas(sede_id)


@router.get("/plazas", response_model=List[PlazaRead])
async def listar_plazas(
    sede_id: str,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    zona: Optional[str] = None,
    tipo: Optional[TipoEspacio] = None,
    service: EspacioService = Depends(get_espacio_service),
):
    """Grilla de plazas con su estado (disponible/ocupada/reservada/mantenimiento) para el horario."""
    return await service.plazas(sede_id, zona, tipo, fecha_inicio, fecha_fin)


@router.get("/disponibles", response_model=List[EspacioRead])
async def listar_espacios_disponibles(
    sede_id: str,
    tipo: TipoEspacio,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    service: EspacioService = Depends(get_espacio_service),
):
    """Espacios sin reservas que se crucen con el horario pedido."""
    return await service.disponibles(sede_id, tipo, fecha_inicio, fecha_fin)


@router.get("/{espacio_id}", response_model=EspacioRead)
async def obtener_espacio(espacio_id: str, service: EspacioService = Depends(get_espacio_service)):
    return await service.obtener(espacio_id)


@router.post("", response_model=EspacioRead, status_code=status.HTTP_201_CREATED)
async def crear_espacio(
    data: EspacioCreate,
    admin: Document = Depends(require_permiso("gestionar_sedes")),
    service: EspacioService = Depends(get_espacio_service),
):
    return await service.crear(admin, data)


@router.patch("/{espacio_id}", response_model=EspacioRead)
async def actualizar_espacio(
    espacio_id: str,
    data: EspacioUpdate,
    admin: Document = Depends(require_permiso("gestionar_sedes")),
    service: EspacioService = Depends(get_espacio_service),
):
    return await service.actualizar(admin, espacio_id, data)
