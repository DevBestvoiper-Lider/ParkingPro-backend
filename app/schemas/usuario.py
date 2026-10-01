from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import MongoModel


class VehiculoCreate(BaseModel):
    placa: str = Field(min_length=5, max_length=10)
    marca: Optional[str] = None
    modelo: Optional[str] = None
    color: Optional[str] = None

    @field_validator("placa")
    @classmethod
    def normalizar_placa(cls, value: str) -> str:
        return value.replace(" ", "").replace("-", "").upper()


class VehiculoRead(MongoModel):
    placa: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    color: Optional[str] = None


class UsuarioCreate(BaseModel):
    nombre: str = Field(min_length=1)
    email: EmailStr
    telefono: Optional[str] = None
    password: str = Field(min_length=8)


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1)
    telefono: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)


class UsuarioRead(MongoModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    vehiculos: List[VehiculoRead] = []
