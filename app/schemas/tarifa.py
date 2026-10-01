from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import TipoVehiculo
from app.schemas.common import MongoModel, Money, ObjectIdStr, PyObjectId


class TarifaCreate(BaseModel):
    sede_id: ObjectIdStr
    nombre: str = Field(min_length=1)
    tipo_vehiculo: TipoVehiculo
    valor_hora: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class TarifaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1)
    tipo_vehiculo: Optional[TipoVehiculo] = None
    valor_hora: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class TarifaRead(MongoModel):
    parqueadero_id: PyObjectId
    sede_id: PyObjectId
    nombre: str
    tipo_vehiculo: TipoVehiculo
    valor_hora: Money
