from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import EstadoParqueadero, EstadoSede
from app.schemas.common import MongoModel, Money, PyObjectId


class Coordenadas(BaseModel):
    latitud: Optional[float] = Field(default=None, ge=-90, le=90)
    longitud: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validar_par(self) -> "Coordenadas":
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("latitud y longitud van juntas")
        return self


class SedeCreate(Coordenadas):
    nombre: str = Field(min_length=1)
    direccion: str = Field(min_length=1)
    ciudad: str = Field(min_length=1)
    telefono: Optional[str] = None
    estado: EstadoSede = "activa"


class SedeUpdate(Coordenadas):
    nombre: Optional[str] = Field(default=None, min_length=1)
    direccion: Optional[str] = Field(default=None, min_length=1)
    ciudad: Optional[str] = Field(default=None, min_length=1)
    telefono: Optional[str] = None
    estado: Optional[EstadoSede] = None


class SedeRead(MongoModel):
    nombre: str
    direccion: str
    ciudad: str
    telefono: Optional[str] = None
    estado: EstadoSede
    latitud: Optional[float] = None
    longitud: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def desde_ubicacion(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("ubicacion"):
            longitud, latitud = data["ubicacion"]["coordinates"]
            data = {**data, "latitud": latitud, "longitud": longitud}
        return data


class SedeCercana(BaseModel):
    """Una sede en el mapa: dónde está, a qué distancia, desde cuánto cobra y cuántos cupos tiene."""

    parqueadero_id: PyObjectId
    parqueadero_nombre: str
    sede_id: PyObjectId
    nombre: str
    direccion: str
    ciudad: str
    telefono: Optional[str] = None
    latitud: float
    longitud: float
    distancia_km: float
    precio_hora_desde: Optional[Money] = None
    espacios_libres: int
    espacios_total: int = 0  # plazas operativas (sin mantenimiento) del tipo pedido
    interesados: int = 0  # usuarios viendo esta sede ahora


class AdministradorCreate(BaseModel):
    nombre: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)


class ParqueaderoCreate(BaseModel):
    nombre: str = Field(min_length=1)
    nit: str = Field(min_length=3)
    email_contacto: EmailStr
    telefono: Optional[str] = None
    administrador: AdministradorCreate


class ParqueaderoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1)
    email_contacto: Optional[EmailStr] = None
    telefono: Optional[str] = None


class ParqueaderoRead(MongoModel):
    nombre: str
    nit: str
    email_contacto: str
    telefono: Optional[str] = None
    estado: EstadoParqueadero
    fecha_registro: datetime
    sedes: List[SedeRead] = []
