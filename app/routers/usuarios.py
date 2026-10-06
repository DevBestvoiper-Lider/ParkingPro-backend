from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_usuario, get_usuario_service
from app.repositories.base import Document
from app.schemas.usuario import UsuarioRead, UsuarioUpdate, VehiculoCreate
from app.services.usuario_service import UsuarioService

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/me", response_model=UsuarioRead)
async def leer_usuario_actual(usuario: Document = Depends(get_current_usuario)):
    return usuario


@router.patch("/me", response_model=UsuarioRead)
async def actualizar_usuario_actual(
    data: UsuarioUpdate,
    usuario: Document = Depends(get_current_usuario),
    service: UsuarioService = Depends(get_usuario_service),
):
    return await service.actualizar(usuario, data)


@router.post("/me/vehiculos", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def agregar_vehiculo(
    data: VehiculoCreate,
    usuario: Document = Depends(get_current_usuario),
    service: UsuarioService = Depends(get_usuario_service),
):
    return await service.agregar_vehiculo(usuario, data)


@router.patch("/me/vehiculos/{vehiculo_id}", response_model=UsuarioRead)
async def actualizar_vehiculo(
    vehiculo_id: str,
    data: VehiculoCreate,
    usuario: Document = Depends(get_current_usuario),
    service: UsuarioService = Depends(get_usuario_service),
):
    return await service.actualizar_vehiculo(usuario, vehiculo_id, data)


@router.delete("/me/vehiculos/{vehiculo_id}", response_model=UsuarioRead)
async def eliminar_vehiculo(
    vehiculo_id: str,
    usuario: Document = Depends(get_current_usuario),
    service: UsuarioService = Depends(get_usuario_service),
):
    return await service.eliminar_vehiculo(usuario, vehiculo_id)
