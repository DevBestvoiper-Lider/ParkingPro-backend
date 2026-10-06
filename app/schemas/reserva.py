from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.core.billing import calcular_total
from app.core.utils import utcnow
from app.models.enums import EstadoPago, EstadoReserva, EstadoSesion, MetodoPago, TipoEspacio
from app.schemas.common import MongoModel, Money, ObjectIdStr, PyObjectId


class ReservaCreate(BaseModel):
    sede_id: ObjectIdStr
    espacio_id: ObjectIdStr
    tarifa_id: ObjectIdStr
    vehiculo_id: ObjectIdStr
    fecha_inicio: datetime
    fecha_fin: datetime

    @model_validator(mode="after")
    def validar_fechas(self) -> "ReservaCreate":
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior a fecha_inicio")
        return self


class TarifaAplicada(BaseModel):
    nombre: str
    valor_hora: Money
    descuento_pct: Optional[int] = None  # plan Afiliado


class Sesion(BaseModel):
    hora_entrada: Optional[datetime] = None
    hora_salida: Optional[datetime] = None
    estado: EstadoSesion


class PagoCreate(BaseModel):
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    metodo_pago: MetodoPago


class ReembolsoCreate(BaseModel):
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    metodo_pago: MetodoPago


class CheckInManual(BaseModel):
    """Entrada en caseta de un vehículo sin reserva previa."""

    sede_id: ObjectIdStr
    placa: str = Field(min_length=5, max_length=10)
    tipo_espacio: TipoEspacio = "carro"
    espacio_id: Optional[ObjectIdStr] = None  # si no se indica, se asigna uno libre
    tarifa_id: Optional[ObjectIdStr] = None  # si no se indica, la más económica del tipo
    horas_estimadas: int = Field(default=1, ge=1, le=24)
    nombre_cliente: Optional[str] = None

    @field_validator("placa")
    @classmethod
    def normalizar_placa(cls, value: str) -> str:
        return value.replace(" ", "").replace("-", "").upper()


class CheckOutManual(BaseModel):
    placa: str = Field(min_length=5, max_length=10)

    @field_validator("placa")
    @classmethod
    def normalizar_placa(cls, value: str) -> str:
        return value.replace(" ", "").replace("-", "").upper()


class PagoRead(MongoModel):
    codigo: Optional[str] = None
    monto: Money
    fecha_pago: datetime
    metodo_pago: MetodoPago
    estado: EstadoPago


class ReservaRead(MongoModel):
    parqueadero_id: PyObjectId
    sede_id: PyObjectId
    usuario_id: PyObjectId
    vehiculo_id: PyObjectId
    espacio_id: PyObjectId
    tarifa_id: PyObjectId
    codigo: Optional[str] = None
    fecha_inicio: datetime
    fecha_fin: datetime
    estado: EstadoReserva
    tarifa_aplicada: TarifaAplicada
    sesion: Optional[Sesion] = None
    pagos: List[PagoRead] = []

    # Datos de otras colecciones para mostrar sin llamadas extra (no se guardan en la reserva)
    parqueadero_nombre: Optional[str] = None
    sede_nombre: Optional[str] = None
    espacio_codigo: Optional[str] = None
    zona: Optional[str] = None
    placa: Optional[str] = None
    cliente_nombre: Optional[str] = None

    @computed_field
    @property
    def total(self) -> Money:
        """Real si ya salió; hasta ahora si está adentro; si no, el estimado del horario reservado."""
        if self.estado == "cancelada":
            return Decimal("0.00")
        valor_hora = self.tarifa_aplicada.valor_hora
        sesion = self.sesion
        if sesion and sesion.hora_entrada:
            return calcular_total(valor_hora, sesion.hora_entrada, sesion.hora_salida or utcnow())
        return calcular_total(valor_hora, self.fecha_inicio, self.fecha_fin)

    @computed_field
    @property
    def total_pagado(self) -> Money:
        """Pagado menos reembolsado."""
        pagado = sum((p.monto for p in self.pagos if p.estado == "pagado"), Decimal("0.00"))
        reembolsado = sum((p.monto for p in self.pagos if p.estado == "reembolsado"), Decimal("0.00"))
        return pagado - reembolsado

    @computed_field
    @property
    def saldo(self) -> Money:
        return self.total - self.total_pagado


class ResumenUsuario(BaseModel):
    """Datos de la pantalla de Inicio de la app."""

    reservas_proximas: int
    vehiculos: int
    sesion_activa: Optional[ReservaRead] = None
    plan: Literal["por_uso", "afiliado"]
    notificaciones_no_leidas: int


class GastoMes(BaseModel):
    mes: str  # YYYY-MM, hora de Colombia
    total: Money


class UsoFrecuente(BaseModel):
    id: str
    nombre: str
    visitas: int


class ActividadUsuario(BaseModel):
    """Pantalla Mi actividad. Sale de las reservas; no se guarda aparte."""

    total_gastado: Money
    gasto_por_mes: List[GastoMes]
    tendencia_pct: Optional[float] = None  # mes actual contra el anterior; null si el anterior fue $0
    horas_estacionado: float
    reservas_completadas: int
    reservas_canceladas: int
    sedes_mas_usadas: List[UsoFrecuente]
    vehiculos_mas_usados: List[UsoFrecuente]
    promedio_por_visita: Money
    ahorro_afiliado: Money
    ahorro_es_estimado: bool  # true: cuánto habría ahorrado con el plan; false: ahorro ya aplicado
