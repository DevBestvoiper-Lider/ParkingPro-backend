from collections import Counter
from typing import Optional

from fastapi import HTTPException, status

from app.core.realtime import HubTiempoReal
from app.core.utils import parse_oid
from app.repositories.base import Document
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.interes_repository import InteresRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository


class InteresService:
    """'Cuántas personas están viendo este parqueadero/plaza' para gestionar la demanda."""

    def __init__(
        self,
        repository: InteresRepository,
        parqueaderos: ParqueaderoRepository,
        espacios: EspacioRepository,
        hub: HubTiempoReal,
    ):
        self.repository = repository
        self.parqueaderos = parqueaderos
        self.espacios = espacios
        self.hub = hub

    async def marcar(self, sede_id: str, clave: str, espacio_id: Optional[str]) -> Document:
        """La app lo llama al abrir una sede y cada ~1 min mientras siga en pantalla."""
        sid = parse_oid(sede_id)
        if not await self.parqueaderos.get_sede(sid):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        eid = None
        if espacio_id:
            eid = parse_oid(espacio_id)
            if not await self.espacios.exists({"_id": eid, "sede_id": sid}):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado en la sede")
        await self.repository.marcar(sid, clave, eid)
        conteo = await self.consultar(sede_id)
        await self.hub.publicar(sede_id, {"evento": "interes", **conteo})
        return conteo

    async def consultar(self, sede_id: str) -> Document:
        vigentes = await self.repository.vigentes([parse_oid(sede_id)])
        por_espacio = Counter(str(i["espacio_id"]) for i in vigentes if i.get("espacio_id"))
        return {"sede_id": sede_id, "viendo": len(vigentes), "por_espacio": dict(por_espacio)}
