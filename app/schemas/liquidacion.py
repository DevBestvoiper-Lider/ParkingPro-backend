from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.common import MongoModel, Money


class Conceptos(BaseModel):
    pagos_app: Money
    compensacion: Money
    comision_app: Money
    comision_caja: Money
    reembolsos_app: Money
    saldo_anterior: Money
    total: Money  # positivo: ParkingPro le transfiere al socio; negativo: el socio debe


class LiquidacionRead(MongoModel, Conceptos):
    semana_inicio: datetime
    semana_fin: datetime
    estado: Literal["pendiente", "trasladada", "pagada"]
    fecha_generada: datetime


class CuentaRead(Conceptos):
    desde: datetime
    hasta: datetime
    deuda: Money
    limite_deuda: Money
    uso_limite_pct: int
    comision_pct: int
    excedida_desde: Optional[datetime] = None
