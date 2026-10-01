from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.enums import EstadoEspacio, EstadoPlaza, TipoEspacio
from app.schemas.common import MongoModel, ObjectIdStr, PyObjectId


class EspacioCreate(BaseModel):
    sede_id: ObjectIdStr
    codigo: str = Field(min_length=1)
    zona: Optional[str] = None
    tipo: TipoEspacio
    estado: Literal["disponible", "mantenimiento"] = "disponible"


class EspacioUpdate(BaseModel):
    codigo: Optional[str] = Field(default=None, min_length=1)
    zona: Optional[str] = None
    tipo: Optional[TipoEspacio] = None
    # "ocupado" solo lo asignan la entrada/salida de una reserva
    estado: Optional[Literal["disponible", "mantenimiento"]] = None


class EspacioRead(MongoModel):
    parqueadero_id: PyObjectId
    sede_id: PyObjectId
    codigo: str
    zona: Optional[str] = None
    tipo: TipoEspacio
    estado: EstadoEspacio


class PlazaRead(EspacioRead):
    """Espacio con su estado para el horario consultado (grilla de 'Selecciona tu plaza')."""

    estado_horario: EstadoPlaza
    interesados: int = 0  # usuarios viendo esta plaza ahora


class ZonaRead(BaseModel):
    zona: str
    plazas: int
