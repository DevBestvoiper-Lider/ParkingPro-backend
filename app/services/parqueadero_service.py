import re
from typing import List, Optional, Union

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.comision import condiciones_parqueadero, condiciones_socio
from app.core.security import hash_password
from app.core.utils import clean, parse_oid, punto, utcnow
from app.models.enums import PERMISOS
from app.repositories.auditoria_repository import AuditoriaRepository, cambios_de
from app.repositories.base import Document
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.socio_repository import SocioRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.parqueadero import (
    AdministradorCreate, ParqueaderoCreate, ParqueaderoNuevo, ParqueaderoUpdate, SedeCreate, SedeUpdate,
)

class ParqueaderoService:
    def __init__(
        self,
        repository: ParqueaderoRepository,
        empleados: EmpleadoRepository,
        socios: SocioRepository,
        usuarios: UsuarioRepository,
        auditoria: AuditoriaRepository,
    ):
        self.repository = repository
        self.empleados = empleados
        self.socios = socios
        self.usuarios = usuarios
        self.auditoria = auditoria

    async def registrar(self, data: ParqueaderoCreate) -> Document:
        """Alta pública: la cuenta del socio y su primer parqueadero ('en_prueba')."""
        email = data.socio.email.lower()
        if (
            await self.socios.get_by_email(email)
            or await self.usuarios.get_by_email(email)
            or await self.empleados.get_by_email(email)
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "El email del socio ya está registrado. Si ya eres socio, agrega el parqueadero desde tu portafolio",
            )
        if data.administrador and data.administrador.email.lower() == email:
            raise HTTPException(status.HTTP_409_CONFLICT, "El socio y el administrador necesitan cuentas separadas")
        await self._validar_nuevo(data)
        ahora = utcnow()
        socio = await self.socios.insert(clean({
            "nombre": data.socio.nombre,
            "email": email,
            "telefono": data.socio.telefono,
            "estado": "activo",
            "fecha_registro": ahora,
            "password_hash": hash_password(data.socio.password),
            "sesion_version": 0,
            "condiciones": condiciones_socio(),
            "liquida_desde": ahora,
        }))
        actor = {**socio, "cuenta": "socio"}
        await self.auditoria.registrar(actor, "crear", "socio", socio["_id"], despues={
            "nombre": socio["nombre"], "email": email, "condiciones": socio["condiciones"],
        })
        return await self._crear(actor, data)

    async def agregar(self, socio: Document, data: ParqueaderoNuevo) -> Document:
        """Un parqueadero más en el portafolio del socio."""
        await self._validar_nuevo(data)
        return await self._crear(socio, data)

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

    async def actualizar(self, parqueadero_id: str, data: ParqueaderoUpdate, actor: Document) -> Document:
        pid = self._propio(parqueadero_id, actor)
        cambios = clean(data.model_dump())
        if "email_contacto" in cambios:
            cambios["email_contacto"] = cambios["email_contacto"].lower()
        anterior = await self.obtener(parqueadero_id)
        if not cambios:
            return anterior
        actualizado = await self.repository.update(pid, cambios)
        await self.auditoria.registrar(actor, "actualizar", "parqueadero", pid, pid, **cambios_de(anterior, cambios))
        return actualizado

    async def agregar_sede(self, parqueadero_id: str, data: SedeCreate, actor: Document) -> Document:
        pid = self._propio(parqueadero_id, actor)
        sede = {"_id": ObjectId(), **self._campos_sede(data)}
        actualizado = await self.repository.add_sede(pid, sede)
        await self.auditoria.registrar(actor, "crear", "sede", sede["_id"], pid, despues=sede)
        return actualizado

    async def actualizar_sede(self, parqueadero_id: str, sede_id: str, data: SedeUpdate, actor: Document) -> Document:
        pid = self._propio(parqueadero_id, actor)
        cambios = self._campos_sede(data)
        if not cambios:
            return await self.obtener(parqueadero_id)
        sid = parse_oid(sede_id)
        encontrado = await self.repository.get_sede(sid)
        actualizado = await self.repository.update_sede(pid, sid, cambios)
        if not encontrado or not actualizado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        await self.auditoria.registrar(actor, "actualizar", "sede", sid, pid, **cambios_de(encontrado[1], cambios))
        return actualizado

    async def _validar_nuevo(self, data: ParqueaderoNuevo) -> None:
        if await self.repository.exists({"nit": data.nit}):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un parqueadero con ese NIT")
        if data.administrador and await self._email_de_personal(data.administrador.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "El email del administrador ya está registrado")

    async def _email_de_personal(self, email: str) -> bool:
        return bool(await self.empleados.get_by_email(email) or await self.socios.get_by_email(email))

    async def _crear(self, actor: Document, data: ParqueaderoNuevo) -> Document:
        ahora = utcnow()
        parqueadero = await self.repository.insert(clean({
            "nombre": data.nombre,
            "nit": data.nit,
            "email_contacto": data.email_contacto.lower(),
            "telefono": data.telefono,
            "estado": "en_prueba",
            "fecha_registro": ahora,
            "socio_id": actor["_id"],
            "condiciones": condiciones_parqueadero(ahora),
            "sedes": [],
        }))
        pid = parqueadero["_id"]
        await self.auditoria.registrar(actor, "crear", "parqueadero", pid, pid, despues={
            "nombre": data.nombre, "nit": data.nit, "condiciones": parqueadero["condiciones"],
        })
        if data.administrador:
            await self._primer_administrador(actor, pid, data.administrador)
        return parqueadero

    async def _primer_administrador(self, actor: Document, pid: ObjectId, admin: AdministradorCreate) -> None:
        permisos = sorted(PERMISOS)
        empleado = await self.empleados.insert({
            "accesos": [{"parqueadero_id": pid, "permisos": permisos}],
            "nombre": admin.nombre,
            "email": admin.email.lower(),
            "rol": "administrador",
            "estado": "activo",
            "password_hash": hash_password(admin.password),
            "sesion_version": 0,
        })
        await self.auditoria.registrar(actor, "crear", "empleado", empleado["_id"], pid, despues={
            "nombre": admin.nombre, "email": empleado["email"], "rol": "administrador", "permisos": permisos,
        })

    @staticmethod
    def _campos_sede(data: Union[SedeCreate, SedeUpdate]) -> Document:
        campos = clean(data.model_dump(exclude={"latitud", "longitud"}))
        if data.latitud is not None:
            campos["ubicacion"] = punto(data.latitud, data.longitud)
        return campos

    @staticmethod
    def _propio(parqueadero_id: str, actor: Document) -> ObjectId:
        pid = parse_oid(parqueadero_id)
        if pid != actor["parqueadero_id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No administras este parqueadero")
        return pid
