from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from app.models.enums import EstadoSuscripcion, PlanUsuario, TipoEspacio
from app.schemas.common import MongoModel, Money, ObjectIdStr, PyObjectId


class PlanRead(BaseModel):
    plan: PlanUsuario
    nombre: str
    precio_mensual: Money
    descuento_pct: int
    beneficios: List[str]
    recomendado_para: str


class SuscripcionCreate(BaseModel):
    metodo_pago: Literal["tarjeta", "app"] = "app"
    renovacion_automatica: bool = True


class SuscripcionRead(MongoModel):
    usuario_id: PyObjectId
    plan: Literal["afiliado"]
    precio: Money
    descuento_pct: int
    fecha_inicio: datetime
    fecha_fin: datetime
    estado: EstadoSuscripcion
    renovacion_automatica: bool = False


class AlertaCreate(BaseModel):
    sede_id: ObjectIdStr
    tipo: Optional[TipoEspacio] = None


class AlertaRead(MongoModel):
    sede_id: PyObjectId
    tipo: Optional[TipoEspacio] = None
    fecha_creacion: datetime
    ultima_notificacion: Optional[datetime] = None


class NotificacionRead(MongoModel):
    titulo: str
    mensaje: str
    leida: bool
    fecha: datetime
    reserva_id: Optional[PyObjectId] = None
    sede_id: Optional[PyObjectId] = None
