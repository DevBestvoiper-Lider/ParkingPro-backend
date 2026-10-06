from dataclasses import dataclass
from typing import Any, Dict, Literal

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field

TipoCuenta = Literal["usuario", "empleado"]


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
    """Quién hace la petición: un usuario (cliente) o un empleado del parqueadero."""

    tipo: TipoCuenta
    doc: Dict[str, Any]

    @property
    def id(self) -> ObjectId:
        return self.doc["_id"]

    @property
    def es_usuario(self) -> bool:
        return self.tipo == "usuario"

    @property
    def es_empleado(self) -> bool:
        return self.tipo == "empleado"
