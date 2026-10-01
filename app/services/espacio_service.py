from collections import Counter
from datetime import datetime
from typing import List, Optional, Set, Tuple

from bson import ObjectId

from fastapi import HTTPException, status

from app.core.utils import as_utc, clean, parse_oid, utcnow
from app.repositories.base import Document
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.interes_repository import InteresRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.reserva_repository import ReservaRepository
from app.schemas.espacio import EspacioCreate, EspacioUpdate
from app.services.eventos import Eventos


class EspacioService:
    def __init__(
        self,
        repository: EspacioRepository,
        parqueaderos: ParqueaderoRepository,
        reservas: ReservaRepository,
        interesados: InteresRepository,
        eventos: Eventos,
    ):
        self.repository = repository
        self.parqueaderos = parqueaderos
        self.reservas = reservas
        self.interesados = interesados
        self.eventos = eventos

    async def listar(
        self, sede_id: str, zona: Optional[str], tipo: Optional[str], estado: Optional[str], skip: int, limit: int
    ) -> List[Document]:
        filtro = clean({"sede_id": parse_oid(sede_id), "zona": zona, "tipo": tipo, "estado": estado})
        return await self.repository.find(filtro, skip, limit, sort=[("zona", 1), ("codigo", 1)])

    async def zonas(self, sede_id: str) -> List[Document]:
        """Zonas de la sede con su cantidad de plazas (para el selector de zona)."""
        conteo = Counter(e.get("zona") or "Sin zona" for e in await self.repository.find({"sede_id": parse_oid(sede_id)}, limit=0))
        return [{"zona": z, "plazas": n} for z, n in sorted(conteo.items())]

    async def plazas(
        self, sede_id: str, zona: Optional[str], tipo: Optional[str], inicio: datetime, fin: datetime
    ) -> List[Document]:
        """Todos los espacios de la sede con su `estado_horario` para [inicio, fin)."""
        inicio, fin = _rango(inicio, fin)
        espacios = await self.repository.find(
            clean({"sede_id": parse_oid(sede_id), "zona": zona, "tipo": tipo}),
            limit=0,
            sort=[("zona", 1), ("codigo", 1)],
        )
        reservados = await self.reservas.espacios_reservados([e["_id"] for e in espacios], inicio, fin)
        empieza_ya = inicio <= utcnow()
        interes = Counter(
            i["espacio_id"] for i in await self.interesados.vigentes([parse_oid(sede_id)]) if i.get("espacio_id")
        )
        for espacio in espacios:
            espacio["estado_horario"] = _estado_horario(espacio, reservados, empieza_ya)
            espacio["interesados"] = interes.get(espacio["_id"], 0)
        return espacios

    async def disponibles(self, sede_id: str, tipo: str, inicio: datetime, fin: datetime) -> List[Document]:
        plazas = await self.plazas(sede_id, None, tipo, inicio, fin)
        return [p for p in plazas if p["estado_horario"] == "disponible"]

    async def obtener(self, espacio_id: str) -> Document:
        espacio = await self.repository.get(parse_oid(espacio_id))
        if not espacio:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado")
        return espacio

    async def crear(self, admin: Document, data: EspacioCreate) -> Document:
        sede_id = parse_oid(data.sede_id)
        encontrado = await self.parqueaderos.get_sede(sede_id)
        if not encontrado or encontrado[0]["_id"] != admin["parqueadero_id"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        if await self.repository.exists({"sede_id": sede_id, "codigo": data.codigo}):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un espacio con ese código en la sede")
        return await self.repository.insert(clean({
            "parqueadero_id": admin["parqueadero_id"],
            "sede_id": sede_id,
            "codigo": data.codigo,
            "zona": data.zona,
            "tipo": data.tipo,
            "estado": data.estado,
        }))

    async def actualizar(self, admin: Document, espacio_id: str, data: EspacioUpdate) -> Document:
        eid = parse_oid(espacio_id)
        espacio = await self.repository.get(eid, parqueadero_id=admin["parqueadero_id"])
        if not espacio:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado")
        cambios = clean(data.model_dump())
        if not cambios:
            return espacio
        if espacio["estado"] == "ocupado" and ("estado" in cambios or "tipo" in cambios):
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio está ocupado; registra la salida primero")
        if "codigo" in cambios and cambios["codigo"] != espacio["codigo"]:
            if await self.repository.exists({"sede_id": espacio["sede_id"], "codigo": cambios["codigo"]}):
                raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un espacio con ese código en la sede")
        actualizado = await self.repository.update(eid, cambios)
        if cambios.get("estado", espacio["estado"]) != espacio["estado"]:
            nombre = " - ".join(p for p in (actualizado.get("zona"), f"Plaza {actualizado['codigo']}") if p)
            texto = "en mantenimiento" if cambios["estado"] == "mantenimiento" else "disponible de nuevo"
            await self.eventos.registrar(
                actualizado["parqueadero_id"], actualizado["sede_id"], "espacio_estado", f"{nombre} {texto}",
                espacio_id=eid, estado_espacio=cambios["estado"],
            )
        return actualizado


def _rango(inicio: datetime, fin: datetime) -> Tuple[datetime, datetime]:
    inicio, fin = as_utc(inicio), as_utc(fin)
    if fin <= inicio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "fecha_fin debe ser posterior a fecha_inicio")
    return inicio, fin


def _estado_horario(espacio: Document, reservados: Set[ObjectId], empieza_ya: bool) -> str:
    if espacio["estado"] == "mantenimiento":
        return "mantenimiento"
    # Un carro parqueado ahora solo importa si el horario pedido arranca ya.
    if espacio["estado"] == "ocupado" and empieza_ya:
        return "ocupada"
    if espacio["_id"] in reservados:
        return "reservada"
    return "disponible"
