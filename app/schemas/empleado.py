from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import EstadoEmpleado, RolEmpleado
from app.schemas.common import MongoModel, PyObjectId


class EmpleadoCreate(BaseModel):
    nombre: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    rol: RolEmpleado = "operador"


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1)
    rol: Optional[RolEmpleado] = None
    estado: Optional[EstadoEmpleado] = None
    password: Optional[str] = Field(default=None, min_length=8)


class EmpleadoRead(MongoModel):
    parqueadero_id: PyObjectId
    nombre: str
    email: str
    rol: RolEmpleado
    estado: EstadoEmpleado
