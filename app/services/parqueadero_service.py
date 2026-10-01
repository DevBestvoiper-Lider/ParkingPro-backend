import re
from typing import List, Optional, Union

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.security import hash_password
from app.core.utils import clean, parse_oid, punto, utcnow
from app.repositories.base import Document
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.schemas.parqueadero import ParqueaderoCreate, ParqueaderoUpdate, SedeCreate, SedeUpdate


class ParqueaderoService:
    def __init__(self, repository: ParqueaderoRepository, empleados: EmpleadoRepository):
        self.repository = repository
        self.empleados = empleados

    async def registrar(self, data: ParqueaderoCreate) -> Document:
        """Alta de un parqueadero nuevo (queda 'en_prueba') junto con su primer administrador."""
        if await self.repository.exists({"nit": data.nit}):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un parqueadero con ese NIT")
        admin = data.administrador
        if await self.empleados.get_by_email(admin.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "El email del administrador ya está registrado")

        parqueadero = await self.repository.insert(clean({
            "nombre": data.nombre,
            "nit": data.nit,
            "email_contacto": data.email_contacto.lower(),
            "telefono": data.telefono,
            "estado": "en_prueba",
            "fecha_registro": utcnow(),
            "sedes": [],
        }))
        await self.empleados.insert({
            "parqueadero_id": parqueadero["_id"],
            "nombre": admin.nombre,
            "email": admin.email.lower(),
            "rol": "administrador",
            "estado": "activo",
            "password_hash": hash_password(admin.password),
        })
        return parqueadero

    async def listar(self, ciudad: Optional[str], skip: int, limit: int) -> List[Document]:
        filtro: Document = {"estado": {"$ne": "suspendido"}}
        if ciudad:
            filtro["sedes.ciudad"] = {"$regex": f"^{re.escape(ciudad)}$", "$options": "i"}
        return await self.repository.find(filtro, skip, limit, sort=[("nombre", 1)])

    async def obtener(self, parqueadero_id: str) -> Document:
        parqueadero = await self.repository.get(parse_oid(parqueadero_id))
        if not parqueadero:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Parqueadero no encontrado")
        return parqueadero

    async def actualizar(self, parqueadero_id: str, data: ParqueaderoUpdate, admin: Document) -> Document:
        pid = self._propio(parqueadero_id, admin)
        cambios = clean(data.model_dump())
        if "email_contacto" in cambios:
            cambios["email_contacto"] = cambios["email_contacto"].lower()
        if not cambios:
            return await self.obtener(parqueadero_id)
        return await self.repository.update(pid, cambios)

    async def agregar_sede(self, parqueadero_id: str, data: SedeCreate, admin: Document) -> Document:
        pid = self._propio(parqueadero_id, admin)
        sede = {"_id": ObjectId(), **self._campos_sede(data)}
        return await self.repository.add_sede(pid, sede)

    async def actualizar_sede(self, parqueadero_id: str, sede_id: str, data: SedeUpdate, admin: Document) -> Document:
        pid = self._propio(parqueadero_id, admin)
        cambios = self._campos_sede(data)
        if not cambios:
            return await self.obtener(parqueadero_id)
        actualizado = await self.repository.update_sede(pid, parse_oid(sede_id), cambios)
        if not actualizado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        return actualizado

    @staticmethod
    def _campos_sede(data: Union[SedeCreate, SedeUpdate]) -> Document:
        campos = clean(data.model_dump(exclude={"latitud", "longitud"}))
        if data.latitud is not None:
            campos["ubicacion"] = punto(data.latitud, data.longitud)
        return campos

    @staticmethod
    def _propio(parqueadero_id: str, admin: Document) -> ObjectId:
        pid = parse_oid(parqueadero_id)
        if pid != admin["parqueadero_id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No administras este parqueadero")
        return pid
