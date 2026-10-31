from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field

TipoCuenta = Literal["usuario", "empleado", "socio"]


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tipo: TipoCuenta


class RefreshRequest(BaseModel):
    refresh_token: str


class RecuperarClave(BaseModel):
    email: EmailStr


class RestablecerClave(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=8)


class Mensaje(BaseModel):
    mensaje: str


@dataclass
class Principal:
    """Quién hace la petición: un usuario (cliente), un empleado del parqueadero o un socio (dueño).

    Para empleados y socios, `doc` lleva además `parqueadero_id` (el parqueadero en el que actúan),
    `permisos` en ese parqueadero y `cuenta` (empleado o socio).
    """

    tipo: TipoCuenta
    doc: Dict[str, Any]
    permisos: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def id(self) -> ObjectId:
        return self.doc["_id"]

    @property
    def es_usuario(self) -> bool:
        return self.tipo == "usuario"

    @property
    def es_empleado(self) -> bool:
        return self.tipo == "empleado"

    @property
    def es_personal(self) -> bool:
        """Empleado o socio: opera un parqueadero desde el panel."""
        return self.tipo in ("empleado", "socio")

    @property
    def parqueadero_id(self) -> Optional[ObjectId]:
        return self.doc.get("parqueadero_id")
