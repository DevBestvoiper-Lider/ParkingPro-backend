from typing import List, Optional

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_admin, get_tarifa_service
from app.models.enums import TipoVehiculo
from app.repositories.base import Document
from app.schemas.tarifa import TarifaCreate, TarifaRead, TarifaUpdate
from app.services.tarifa_service import TarifaService

router = APIRouter(prefix="/tarifas", tags=["tarifas"])


@router.get("", response_model=List[TarifaRead])
async def listar_tarifas(
    sede_id: str,
    tipo_vehiculo: Optional[TipoVehiculo] = None,
    service: TarifaService = Depends(get_tarifa_service),
):
    return await service.listar(sede_id, tipo_vehiculo)


@router.post("", response_model=TarifaRead, status_code=status.HTTP_201_CREATED)
async def crear_tarifa(
    data: TarifaCreate,
    admin: Document = Depends(get_current_admin),
    service: TarifaService = Depends(get_tarifa_service),
):
    return await service.crear(admin, data)


@router.patch("/{tarifa_id}", response_model=TarifaRead)
async def actualizar_tarifa(
    tarifa_id: str,
    data: TarifaUpdate,
    admin: Document = Depends(get_current_admin),
    service: TarifaService = Depends(get_tarifa_service),
):
    return await service.actualizar(admin, tarifa_id, data)


@router.delete("/{tarifa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tarifa(
    tarifa_id: str,
    admin: Document = Depends(get_current_admin),
    service: TarifaService = Depends(get_tarifa_service),
):
    await service.eliminar(admin, tarifa_id)
