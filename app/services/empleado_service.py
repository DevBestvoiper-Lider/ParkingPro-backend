from typing import FrozenSet, Iterable, List, Optional

from fastapi import HTTPException, status

from app.core.security import hash_password
from app.core.utils import parse_oid
from app.models.enums import PERMISOS_POR_ROL
from app.repositories.auditoria_repository import AuditoriaRepository, cambios_de
from app.repositories.base import Document
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.socio_repository import SocioRepository
from app.schemas.empleado import AccesoCreate, EmpleadoCreate, EmpleadoUpdate
from app.services.acceso import accesos, parqueaderos_de, permisos_en

SIN_PERMISOS = HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige al menos un permiso para el administrador")
PERMISOS_FIJOS = HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Operador y cajero tienen permisos fijos")
NO_ENCONTRADO = HTTPException(status.HTTP_404_NOT_FOUND, "Empleado no encontrado")


class EmpleadoService:
    """Empleados de un parqueadero. `actor` es el socio o el administrador que actúa en él."""

    def __init__(
        self,
        repository: EmpleadoRepository,
        parqueaderos: ParqueaderoRepository,
        socios: SocioRepository,
        auditoria: AuditoriaRepository,
    ):
        self.repository = repository
        self.parqueaderos = parqueaderos
        self.socios = socios
        self.auditoria = auditoria

    async def listar(self, actor: Document) -> List[Document]:
        pid = actor["parqueadero_id"]
        filtro = {"$or": [
            {"accesos.parqueadero_id": pid},
            {"accesos": {"$exists": False}, "parqueadero_id": pid},  # empleados sin migrar
        ]}
        return await self.repository.find(filtro, limit=500, sort=[("nombre", 1)])

    async def crear(self, actor: Document, data: EmpleadoCreate) -> Document:
        email = data.email.lower()
        if await self.repository.get_by_email(email) or await self.socios.get_by_email(email):
            raise HTTPException(status.HTTP_409_CONFLICT, "El email ya está registrado")
        if data.rol == "administrador":
            if not data.permisos:
                raise SIN_PERMISOS
            permisos = sorted(set(data.permisos))
            _puede_dar(actor, permisos)
        elif data.permisos is not None:
            raise PERMISOS_FIJOS
        else:
            _puede_dar(actor, PERMISOS_POR_ROL[data.rol])
            permisos = []
        pid = actor["parqueadero_id"]
        empleado = await self.repository.insert({
            "accesos": [{"parqueadero_id": pid, "permisos": permisos}],
            "nombre": data.nombre,
            "email": email,
            "rol": data.rol,
            "estado": "activo",
            "password_hash": hash_password(data.password),
            "sesion_version": 0,
        })
        await self.auditoria.registrar(actor, "crear", "empleado", empleado["_id"], pid, despues={
            "nombre": data.nombre, "email": email, "rol": data.rol, "permisos": permisos,
        })
        return empleado

    async def actualizar(self, actor: Document, empleado_id: str, data: EmpleadoUpdate) -> Document:
        pid = actor["parqueadero_id"]
        empleado, antes = await self._de_este_parqueadero(actor, empleado_id)
        rol = data.rol or empleado["rol"]

        if _es_el_mismo(actor, empleado) and (
            rol != "administrador" or data.estado == "inactivo" or data.permisos is not None
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No puedes quitarte el rol de administrador, desactivarte ni cambiar tus permisos",
            )
        en_otros = len(parqueaderos_de(empleado)) > 1
        cambia_la_cuenta = any(v is not None for v in (data.nombre, data.rol, data.estado, data.password))
        if en_otros and cambia_la_cuenta and actor["cuenta"] != "socio":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Trabaja también en otro parqueadero: aquí solo puedes cambiar sus permisos",
            )
        if en_otros and rol != "administrador":
            raise HTTPException(status.HTTP_409_CONFLICT, "Un operador o cajero trabaja en un solo parqueadero")

        if rol == "administrador":
            if data.permisos is not None:
                guardados = sorted(set(data.permisos))
            elif empleado["rol"] == "administrador":
                guardados = sorted(antes)
            else:
                raise SIN_PERMISOS
            if not guardados:
                raise SIN_PERMISOS
            despues = frozenset(guardados)
        else:
            if data.permisos is not None:
                raise PERMISOS_FIJOS
            guardados = []
            despues = PERMISOS_POR_ROL[rol]
        _puede_dar(actor, antes ^ despues)

        cambios: Document = {
            k: v for k, v in {"nombre": data.nombre, "rol": data.rol, "estado": data.estado}.items() if v is not None
        }
        if despues != antes or "accesos" not in empleado:
            cambios["accesos"] = [
                {**a, "permisos": guardados} if a["parqueadero_id"] == pid else a for a in accesos(empleado)
            ]
        if data.password:
            cambios["password_hash"] = hash_password(data.password)
            cambios["sesion_version"] = empleado.get("sesion_version", 0) + 1
        if not cambios:
            return empleado

        actualizado = await self.repository.update(empleado["_id"], cambios)
        registro = cambios_de(
            {"nombre": empleado["nombre"], "rol": empleado["rol"], "estado": empleado["estado"], "permisos": sorted(antes)},
            {**{k: cambios[k] for k in ("nombre", "rol", "estado") if k in cambios}, "permisos": sorted(despues)},
        )
        if data.password:
            registro["despues"]["clave"] = "cambiada"
        if registro["despues"]:
            await self.auditoria.registrar(actor, "actualizar", "empleado", empleado["_id"], pid, **registro)
        return actualizado

    async def dar_acceso(self, actor: Document, data: AccesoCreate) -> Document:
        """Suma este parqueadero a un administrador que ya trabaja en otro del mismo socio."""
        pid = actor["parqueadero_id"]
        empleado = await self.repository.get_by_email(data.email)
        if not empleado or not await self._mismo_socio(pid, parqueaderos_de(empleado)):
            raise NO_ENCONTRADO
        if permisos_en(empleado, pid) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya trabaja en este parqueadero")
        if empleado["rol"] != "administrador" or empleado["estado"] != "activo":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Solo un administrador activo puede trabajar en varios parqueaderos"
            )
        permisos = sorted(set(data.permisos))
        _puede_dar(actor, permisos)
        nuevos = [*accesos(empleado), {"parqueadero_id": pid, "permisos": permisos}]
        actualizado = await self.repository.update(empleado["_id"], {"accesos": nuevos})
        await self.auditoria.registrar(actor, "dar_acceso", "empleado", empleado["_id"], pid,
                                       despues={"permisos": permisos})
        return actualizado

    async def quitar_acceso(self, actor: Document, empleado_id: str) -> None:
        pid = actor["parqueadero_id"]
        empleado, antes = await self._de_este_parqueadero(actor, empleado_id)
        if _es_el_mismo(actor, empleado):
            raise HTTPException(status.HTTP_409_CONFLICT, "No puedes quitarte el acceso a ti mismo")
        restantes = [a for a in accesos(empleado) if a["parqueadero_id"] != pid]
        if not restantes:
            raise HTTPException(status.HTTP_409_CONFLICT, "Es su único parqueadero: desactívalo en su lugar")
        await self.repository.update(empleado["_id"], {"accesos": restantes})
        await self.auditoria.registrar(actor, "quitar_acceso", "empleado", empleado["_id"], pid,
                                       antes={"permisos": sorted(antes)})

    async def _de_este_parqueadero(self, actor: Document, empleado_id: str):
        """(empleado, sus permisos aquí). Nadie toca a alguien con permisos que él no tiene."""
        empleado = await self.repository.get(parse_oid(empleado_id))
        antes: Optional[FrozenSet[str]] = permisos_en(empleado, actor["parqueadero_id"]) if empleado else None
        if antes is None:
            raise NO_ENCONTRADO
        if not _es_el_mismo(actor, empleado):
            _puede_dar(actor, antes, "No puedes modificar a alguien con permisos que tú no tienes")
        return empleado, antes

    async def _mismo_socio(self, pid, otros: List) -> bool:
        parqueadero = await self.parqueaderos.get(pid)
        if not parqueadero or not parqueadero.get("socio_id") or not otros:
            return False
        return await self.parqueaderos.exists({"_id": {"$in": otros}, "socio_id": parqueadero["socio_id"]})


def _es_el_mismo(actor: Document, empleado: Document) -> bool:
    return actor["cuenta"] == "empleado" and actor["_id"] == empleado["_id"]


def _puede_dar(actor: Document, permisos: Iterable[str], mensaje: str = "No puedes dar ni quitar permisos que no tienes") -> None:
    faltan = set(permisos) - set(actor["permisos"])
    if faltan:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{mensaje}: {', '.join(sorted(faltan))}")
