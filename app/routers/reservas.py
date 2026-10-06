from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.dependencies import (
    get_current_empleado,
    get_current_usuario,
    get_principal,
    get_reserva_service,
    require_roles,
)
from app.models.enums import EstadoReserva
from app.repositories.base import Document
from app.schemas.auth import Principal
from app.schemas.reserva import (
    ActividadUsuario, CheckInManual, CheckOutManual, PagoCreate, ReembolsoCreate, ReservaCreate, ReservaRead,
    ResumenUsuario,
)
from app.services.reserva_service import ReservaService
from app.tasks.background import send_reserva_email

router = APIRouter(prefix="/reservas", tags=["reservas"])


@router.post("", response_model=ReservaRead, status_code=status.HTTP_201_CREATED)
async def crear_reserva(
    data: ReservaCreate,
    background_tasks: BackgroundTasks,
    usuario: Document = Depends(get_current_usuario),
    service: ReservaService = Depends(get_reserva_service),
):
    reserva = await service.crear(usuario, data)
    background_tasks.add_task(send_reserva_email, usuario["email"], str(reserva["_id"]), "creada")
    return reserva


@router.get("/mias/resumen", response_model=ResumenUsuario)
async def resumen_usuario(
    usuario: Document = Depends(get_current_usuario),
    service: ReservaService = Depends(get_reserva_service),
):
    """Pantalla de Inicio: reservas próximas, vehículos y sesión activa."""
    return await service.resumen(usuario)


@router.get("/mias/actividad", response_model=ActividadUsuario)
async def actividad_usuario(
    usuario: Document = Depends(get_current_usuario),
    service: ReservaService = Depends(get_reserva_service),
):
    """Total gastado, horas, sedes y ahorro del plan. Se calcula con las reservas; no hay colección nueva."""
    return await service.actividad(usuario)


@router.get("/mias", response_model=List[ReservaRead])
async def listar_mis_reservas(
    estado: Optional[List[EstadoReserva]] = Query(None, description="Repetible: ?estado=pendiente&estado=confirmada"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    usuario: Document = Depends(get_current_usuario),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.listar_de_usuario(usuario, estado, skip, limit)


@router.get("", response_model=List[ReservaRead])
async def listar_reservas_parqueadero(
    sede_id: Optional[str] = None,
    estado: Optional[List[EstadoReserva]] = Query(None),
    codigo: Optional[str] = None,
    q: Optional[str] = Query(None, description="Busca por placa, cliente o código"),
    zona: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    empleado: Document = Depends(get_current_empleado),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.listar_de_parqueadero(
        empleado, sede_id, estado, codigo, desde, hasta, skip, limit, q=q, zona=zona
    )


@router.post("/check-in-manual", response_model=ReservaRead, status_code=status.HTTP_201_CREATED)
async def check_in_manual(
    data: CheckInManual,
    empleado: Document = Depends(get_current_empleado),
    service: ReservaService = Depends(get_reserva_service),
):
    """Entrada en caseta de un vehículo sin reserva: asigna plaza y tarifa si no se indican."""
    return await service.check_in_manual(empleado, data)


@router.post("/check-out-manual", response_model=ReservaRead)
async def check_out_manual(
    data: CheckOutManual,
    empleado: Document = Depends(get_current_empleado),
    service: ReservaService = Depends(get_reserva_service),
):
    """Salida en caseta buscando la sesión activa por placa."""
    return await service.check_out_manual(empleado, data)


@router.get("/{reserva_id}", response_model=ReservaRead)
async def obtener_reserva(
    reserva_id: str,
    principal: Principal = Depends(get_principal),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.obtener(principal, reserva_id)


@router.post("/{reserva_id}/confirmar", response_model=ReservaRead)
async def confirmar_reserva(
    reserva_id: str,
    empleado: Document = Depends(get_current_empleado),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.confirmar(empleado, reserva_id)


@router.post("/{reserva_id}/cancelar", response_model=ReservaRead)
async def cancelar_reserva(
    reserva_id: str,
    principal: Principal = Depends(get_principal),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.cancelar(principal, reserva_id)


@router.post("/{reserva_id}/entrada", response_model=ReservaRead)
async def registrar_entrada(
    reserva_id: str,
    empleado: Document = Depends(get_current_empleado),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.registrar_entrada(empleado, reserva_id)


@router.post("/{reserva_id}/salida", response_model=ReservaRead)
async def registrar_salida(
    reserva_id: str,
    principal: Principal = Depends(get_principal),
    service: ReservaService = Depends(get_reserva_service),
):
    """Empleado en caseta, o el usuario con 'Finalizar sesión' desde la app."""
    return await service.registrar_salida(principal, reserva_id)


@router.post("/{reserva_id}/pagos", response_model=ReservaRead, status_code=status.HTTP_201_CREATED)
async def registrar_pago(
    reserva_id: str,
    data: PagoCreate,
    principal: Principal = Depends(get_principal),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.registrar_pago(principal, reserva_id, data)


@router.post("/{reserva_id}/reembolsos", response_model=ReservaRead, status_code=status.HTTP_201_CREATED)
async def reembolsar(
    reserva_id: str,
    data: ReembolsoCreate,
    empleado: Document = Depends(require_roles("administrador", "cajero")),
    service: ReservaService = Depends(get_reserva_service),
):
    return await service.reembolsar(empleado, reserva_id, data)
