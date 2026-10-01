from dataclasses import dataclass
from typing import Any, Dict, Literal

from bson import ObjectId
from pydantic import BaseModel

TipoCuenta = Literal["usuario", "empleado"]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tipo: TipoCuenta


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
