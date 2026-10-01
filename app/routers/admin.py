from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.dependencies import get_admin_service, get_current_empleado
from app.models.enums import EstadoPago, EstadoReserva, MetodoPago
from app.repositories.base import Document
from app.schemas.admin import (
    ActividadRead, ClienteRead, Dashboard, EstadisticasReservas, MovimientoPago, Reporte, ResumenPagos,
    VehiculoAdminRead,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["panel web"])

# Las fechas (`fecha`, `desde`, `hasta`) son días en hora local (America/Bogota).


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    sede_id: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.dashboard(empleado, sede_id)


@router.get("/actividad", response_model=List[ActividadRead])
async def actividad(
    sede_id: Optional[str] = None,
    limit: int = Query(30, ge=1, le=200),
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.listar_actividad(empleado, sede_id, limit)


@router.get("/reservas/estadisticas", response_model=EstadisticasReservas)
async def estadisticas_reservas(
    fecha: Optional[date] = None,
    sede_id: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.estadisticas_reservas(empleado, fecha, sede_id)


@router.get("/reservas/exportar")
async def exportar_reservas(
    sede_id: Optional[str] = None,
    estado: Optional[List[EstadoReserva]] = Query(None),
    q: Optional[str] = None,
    zona: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    contenido = await service.exportar_reservas(empleado, sede_id=sede_id, estados=estado, q=q, zona=zona)
    return _descarga(contenido, "reservas.csv")


@router.get("/pagos", response_model=List[MovimientoPago])
async def listar_pagos(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    metodo_pago: Optional[MetodoPago] = None,
    estado: Optional[EstadoPago] = None,
    sede_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.listar_pagos(empleado, desde, hasta, metodo_pago, estado, sede_id, skip, limit)


@router.get("/pagos/resumen", response_model=ResumenPagos)
async def resumen_pagos(
    fecha: Optional[date] = None,
    sede_id: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.resumen_pagos(empleado, fecha, sede_id)


@router.get("/pagos/exportar")
async def exportar_pagos(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    metodo_pago: Optional[MetodoPago] = None,
    estado: Optional[EstadoPago] = None,
    sede_id: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    contenido = await service.exportar_pagos(
        empleado, desde=desde, hasta=hasta, metodo=metodo_pago, estado=estado, sede_id=sede_id
    )
    return _descarga(contenido, "pagos.csv")


@router.get("/clientes", response_model=List[ClienteRead])
async def clientes(
    q: Optional[str] = Query(None, description="Nombre, email o placa"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.clientes(empleado, q, skip, limit)


@router.get("/vehiculos", response_model=List[VehiculoAdminRead])
async def vehiculos(
    q: Optional[str] = Query(None, description="Placa"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    return await service.vehiculos(empleado, q, skip, limit)


@router.get("/reportes", response_model=Reporte)
async def reportes(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    sede_id: Optional[str] = None,
    empleado: Document = Depends(get_current_empleado),
    service: AdminService = Depends(get_admin_service),
):
    """Por defecto, los últimos 30 días."""
    return await service.reporte(empleado, desde, hasta, sede_id)


def _descarga(contenido: str, nombre: str) -> Response:
    # BOM para que Excel abra bien las tildes.
    return Response(
        content="﻿" + contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
