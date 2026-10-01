from typing import List

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_admin, get_current_empleado, get_empleado_service
from app.repositories.base import Document
from app.schemas.empleado import EmpleadoCreate, EmpleadoRead, EmpleadoUpdate
from app.services.empleado_service import EmpleadoService

router = APIRouter(prefix="/empleados", tags=["empleados"])


@router.get("/me", response_model=EmpleadoRead)
async def leer_empleado_actual(empleado: Document = Depends(get_current_empleado)):
    return empleado


@router.get("", response_model=List[EmpleadoRead])
async def listar_empleados(
    admin: Document = Depends(get_current_admin),
    service: EmpleadoService = Depends(get_empleado_service),
):
    return await service.listar(admin)


@router.post("", response_model=EmpleadoRead, status_code=status.HTTP_201_CREATED)
async def crear_empleado(
    data: EmpleadoCreate,
    admin: Document = Depends(get_current_admin),
    service: EmpleadoService = Depends(get_empleado_service),
):
    return await service.crear(admin, data)


@router.patch("/{empleado_id}", response_model=EmpleadoRead)
async def actualizar_empleado(
    empleado_id: str,
    data: EmpleadoUpdate,
    admin: Document = Depends(get_current_admin),
    service: EmpleadoService = Depends(get_empleado_service),
):
    return await service.actualizar(admin, empleado_id, data)
