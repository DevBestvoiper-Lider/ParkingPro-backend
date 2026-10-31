from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import EstadoSocio
from app.schemas.common import MongoModel


class SocioCreate(BaseModel):
    nombre: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    telefono: Optional[str] = None


class SocioRead(MongoModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    estado: EstadoSocio
    fecha_registro: datetime
