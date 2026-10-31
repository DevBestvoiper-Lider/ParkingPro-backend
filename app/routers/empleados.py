from typing import List

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_empleado, get_empleado_service, require_permiso
from app.repositories.base import Document
from app.schemas.empleado import AccesoCreate, EmpleadoCreate, EmpleadoRead, EmpleadoUpdate
from app.services.empleado_service import EmpleadoService

router = APIRouter(prefix="/empleados", tags=["empleados"])

gestionar_empleados = require_permiso("gestionar_empleados")


@router.get("/me", response_model=EmpleadoRead)
async def leer_empleado_actual(empleado: Document = Depends(get_current_empleado)):
    """Incluye `accesos`: los parqueaderos donde trabaja y sus permisos en cada uno."""
    return empleado


@router.get("", response_model=List[EmpleadoRead])
async def listar_empleados(
    actor: Document = Depends(gestionar_empleados),
    service: EmpleadoService = Depends(get_empleado_service),
):
    return await service.listar(actor)


@router.post("", response_model=EmpleadoRead, status_code=status.HTTP_201_CREATED)
async def crear_empleado(
    data: EmpleadoCreate,
    actor: Document = Depends(gestionar_empleados),
    service: EmpleadoService = Depends(get_empleado_service),
):
    """Un administrador lleva `permisos`; solo se dan los que tiene quien lo crea."""
    return await service.crear(actor, data)


@router.post("/accesos", response_model=EmpleadoRead)
async def dar_acceso(
    data: AccesoCreate,
    actor: Document = Depends(gestionar_empleados),
    service: EmpleadoService = Depends(get_empleado_service),
):
    """Suma este parqueadero a un administrador que ya trabaja en otro del mismo socio."""
    return await service.dar_acceso(actor, data)


@router.patch("/{empleado_id}", response_model=EmpleadoRead)
async def actualizar_empleado(
    empleado_id: str,
    data: EmpleadoUpdate,
    actor: Document = Depends(gestionar_empleados),
    service: EmpleadoService = Depends(get_empleado_service),
):
    """`permisos` cambia lo que puede hacer en este parqueadero."""
    return await service.actualizar(actor, empleado_id, data)


@router.delete("/{empleado_id}/acceso", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_acceso(
    empleado_id: str,
    actor: Document = Depends(gestionar_empleados),
    service: EmpleadoService = Depends(get_empleado_service),
):
    """Deja de trabajar en este parqueadero; conserva los demás."""
    await service.quitar_acceso(actor, empleado_id)
