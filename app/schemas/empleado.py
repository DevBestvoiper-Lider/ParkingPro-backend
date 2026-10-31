from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import EstadoEmpleado, Permiso, RolEmpleado
from app.schemas.common import MongoModel, PyObjectId
from app.services.acceso import accesos, permisos_en


class EmpleadoCreate(BaseModel):
    nombre: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    rol: RolEmpleado = "operador"
    # Solo para un administrador: qué puede hacer en este parqueadero.
    permisos: Optional[List[Permiso]] = None


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1)
    rol: Optional[RolEmpleado] = None
    estado: Optional[EstadoEmpleado] = None
    password: Optional[str] = Field(default=None, min_length=8)
    permisos: Optional[List[Permiso]] = None


class AccesoCreate(BaseModel):
    """Da acceso a este parqueadero a un administrador que ya trabaja en otro del mismo socio."""

    email: EmailStr
    permisos: List[Permiso] = Field(min_length=1)


class AccesoRead(BaseModel):
    parqueadero_id: PyObjectId
    permisos: List[Permiso]


class EmpleadoRead(MongoModel):
    nombre: str
    email: str
    rol: RolEmpleado
    estado: EstadoEmpleado
    accesos: List[AccesoRead] = []

    @model_validator(mode="before")
    @classmethod
    def permisos_efectivos(cls, data: Any) -> Any:
        # Operador y cajero no guardan permisos: se muestran los de su rol.
        if isinstance(data, dict) and "rol" in data:
            data = {**data, "accesos": [
                {"parqueadero_id": a["parqueadero_id"], "permisos": sorted(permisos_en(data, a["parqueadero_id"]))}
                for a in accesos(data)
            ]}
        return data
