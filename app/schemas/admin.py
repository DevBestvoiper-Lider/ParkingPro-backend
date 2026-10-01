from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from app.models.enums import EstadoPago, MetodoPago, TipoActividad
from app.schemas.common import MongoModel, Money, PyObjectId
from app.schemas.reserva import ReservaRead
from app.schemas.usuario import VehiculoRead


class ConteoPlazas(BaseModel):
    total: int
    disponibles: int
    ocupadas: int
    reservadas: int  # con reserva en la próxima hora
    mantenimiento: int


class OcupacionZona(ConteoPlazas):
    zona: str
    porcentaje_del_total: float
    porcentaje_ocupacion: float  # (ocupadas + reservadas) / total


class IngresoDia(BaseModel):
    fecha: date
    total: Money


class Alerta(BaseModel):
    tipo: str  # mantenimiento | capacidad | pendientes_pago
    titulo: str
    detalle: str


class ActividadRead(MongoModel):
    sede_id: PyObjectId
    tipo: TipoActividad
    descripcion: str
    reserva_id: Optional[PyObjectId] = None
    espacio_id: Optional[PyObjectId] = None
    fecha: datetime


class Dashboard(BaseModel):
    plazas: ConteoPlazas
    ingresos_hoy: Money
    ingresos_ayer: Money
    variacion_ingresos_pct: Optional[float]
    ocupacion_por_zona: List[OcupacionZona]
    ingresos_ultimos_7_dias: List[IngresoDia]
    proximas_reservas: List[ReservaRead]
    actividad_reciente: List[ActividadRead]
    alertas: List[Alerta]


class EstadisticasReservas(BaseModel):
    fecha: date
    total: int
    variacion_vs_ayer: int
    confirmadas: int
    pendientes: int
    completadas: int
    canceladas: int
    pendientes_de_pago: int
    monto_pendiente: Money


class MovimientoPago(MongoModel):
    """Un pago o reembolso con los datos de su reserva (tabla de Pagos)."""

    codigo: Optional[str] = None
    reserva_id: PyObjectId
    reserva_codigo: Optional[str] = None
    cliente_nombre: Optional[str] = None
    placa: Optional[str] = None
    metodo_pago: MetodoPago
    monto: Money
    estado: EstadoPago
    fecha_pago: datetime


class ResumenMetodo(BaseModel):
    metodo_pago: MetodoPago
    monto: Money
    porcentaje: float


class ResumenPagos(BaseModel):
    fecha: date
    recaudado: Money
    recaudado_ayer: Money
    variacion_pct: Optional[float]
    pendientes_monto: Money
    pendientes_reservas: int
    transacciones: int
    reembolsos_cantidad: int
    reembolsos_monto: Money
    metodos: List[ResumenMetodo]
    ticket_promedio: Money


class ClienteRead(MongoModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    vehiculos: List[VehiculoRead] = []
    afiliado: bool
    reservas: int
    total_pagado: Money
    ultima_visita: Optional[datetime] = None


class VehiculoAdminRead(VehiculoRead):
    cliente_id: PyObjectId
    cliente_nombre: str
    visitas: int
    ultima_visita: Optional[datetime] = None
    adentro: bool  # tiene una sesión activa ahora


class HoraPico(BaseModel):
    hora: int  # 0-23, hora local
    entradas: int


class Reporte(BaseModel):
    desde: date
    hasta: date
    ingresos_total: Money
    ingresos_por_dia: List[IngresoDia]
    ingresos_por_metodo: List[ResumenMetodo]
    reservas_por_estado: Dict[str, int]
    tasa_cancelacion_pct: float
    horas_pico: List[HoraPico]
    duracion_promedio_min: Optional[float]
    ingreso_por_zona: Dict[str, float]
