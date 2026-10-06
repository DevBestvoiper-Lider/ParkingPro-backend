from typing import List

from fastapi import HTTPException, status

from app.core.security import hash_password
from app.core.utils import clean, parse_oid
from app.repositories.base import Document
from app.repositories.empleado_repository import EmpleadoRepository
from app.schemas.empleado import EmpleadoCreate, EmpleadoUpdate


class EmpleadoService:
    def __init__(self, repository: EmpleadoRepository):
        self.repository = repository

    async def listar(self, admin: Document) -> List[Document]:
        return await self.repository.find({"parqueadero_id": admin["parqueadero_id"]}, limit=500, sort=[("nombre", 1)])

    async def crear(self, admin: Document, data: EmpleadoCreate) -> Document:
        email = data.email.lower()
        if await self.repository.get_by_email(email):
            raise HTTPException(status.HTTP_409_CONFLICT, "El email ya está registrado")
        return await self.repository.insert({
            "parqueadero_id": admin["parqueadero_id"],
            "nombre": data.nombre,
            "email": email,
            "rol": data.rol,
            "estado": "activo",
            "password_hash": hash_password(data.password),
            "sesion_version": 0,
        })

    async def actualizar(self, admin: Document, empleado_id: str, data: EmpleadoUpdate) -> Document:
        eid = parse_oid(empleado_id)
        if eid == admin["_id"] and (data.rol not in (None, "administrador") or data.estado == "inactivo"):
            raise HTTPException(status.HTTP_409_CONFLICT, "No puedes quitarte el rol de administrador ni desactivarte")
        empleado = await self.repository.get(eid, parqueadero_id=admin["parqueadero_id"])
        if not empleado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Empleado no encontrado")
        cambios = clean(data.model_dump(exclude={"password"}))
        if data.password:
            cambios["password_hash"] = hash_password(data.password)
            cambios["sesion_version"] = empleado.get("sesion_version", 0) + 1
        if not cambios:
            return empleado
        return await self.repository.update(eid, cambios)
