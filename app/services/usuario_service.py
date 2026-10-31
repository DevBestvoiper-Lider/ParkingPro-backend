from bson import ObjectId
from fastapi import HTTPException, status

from app.core.security import hash_password
from app.core.utils import clean, parse_oid
from app.repositories.base import Document
from app.repositories.socio_repository import SocioRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate, VehiculoCreate


class UsuarioService:
    def __init__(self, repository: UsuarioRepository, socios: SocioRepository):
        self.repository = repository
        self.socios = socios

    async def registrar(self, data: UsuarioCreate) -> Document:
        email = data.email.lower()
        # Un socio parquea con otra cuenta; compartir el email confundiría la recuperación de clave.
        if await self.repository.get_by_email(email) or await self.socios.get_by_email(email):
            raise HTTPException(status.HTTP_409_CONFLICT, "El email ya está registrado")
        return await self.repository.insert(clean({
            "nombre": data.nombre,
            "email": email,
            "telefono": data.telefono,
            "password_hash": hash_password(data.password),
            "sesion_version": 0,
            "vehiculos": [],
        }))

    async def actualizar(self, usuario: Document, data: UsuarioUpdate) -> Document:
        cambios = clean(data.model_dump(exclude={"password"}))
        if data.password:
            cambios["password_hash"] = hash_password(data.password)
            cambios["sesion_version"] = usuario.get("sesion_version", 0) + 1
        if not cambios:
            return usuario
        return await self.repository.update(usuario["_id"], cambios)

    async def agregar_vehiculo(self, usuario: Document, data: VehiculoCreate) -> Document:
        if any(v["placa"] == data.placa for v in usuario.get("vehiculos", [])):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes un vehículo con esa placa")
        vehiculo = {"_id": ObjectId(), **clean(data.model_dump())}
        return await self.repository.add_vehiculo(usuario["_id"], vehiculo)

    async def actualizar_vehiculo(self, usuario: Document, vehiculo_id: str, data: VehiculoCreate) -> Document:
        vid = parse_oid(vehiculo_id)
        vehiculos = usuario.get("vehiculos", [])
        if not any(v["_id"] == vid for v in vehiculos):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehículo no encontrado")
        if any(v["placa"] == data.placa and v["_id"] != vid for v in vehiculos):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes un vehículo con esa placa")
        campos = clean(data.model_dump())
        unset = [campo for campo in ("marca", "modelo", "color") if campo not in campos]
        actualizado = await self.repository.update_vehiculo(usuario["_id"], vid, campos, unset)
        if not actualizado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehículo no encontrado")
        return actualizado

    async def eliminar_vehiculo(self, usuario: Document, vehiculo_id: str) -> Document:
        actualizado = await self.repository.remove_vehiculo(usuario["_id"], parse_oid(vehiculo_id))
        if not actualizado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehículo no encontrado")
        return actualizado
