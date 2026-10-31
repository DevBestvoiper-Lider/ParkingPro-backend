from typing import List, Optional

from fastapi import HTTPException, status

from app.core.utils import clean, parse_oid, to_decimal128
from app.repositories.auditoria_repository import AuditoriaRepository, cambios_de
from app.repositories.base import Document
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.tarifa_repository import TarifaRepository
from app.schemas.tarifa import TarifaCreate, TarifaUpdate


class TarifaService:
    def __init__(self, repository: TarifaRepository, parqueaderos: ParqueaderoRepository, auditoria: AuditoriaRepository):
        self.repository = repository
        self.parqueaderos = parqueaderos
        self.auditoria = auditoria

    async def listar(self, sede_id: str, tipo_vehiculo: Optional[str]) -> List[Document]:
        filtro = clean({"sede_id": parse_oid(sede_id), "tipo_vehiculo": tipo_vehiculo})
        return await self.repository.find(filtro, limit=500, sort=[("nombre", 1)])

    async def crear(self, admin: Document, data: TarifaCreate) -> Document:
        sede_id = parse_oid(data.sede_id)
        encontrado = await self.parqueaderos.get_sede(sede_id)
        if not encontrado or encontrado[0]["_id"] != admin["parqueadero_id"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        tarifa = await self.repository.insert({
            "parqueadero_id": admin["parqueadero_id"],
            "sede_id": sede_id,
            "nombre": data.nombre,
            "tipo_vehiculo": data.tipo_vehiculo,
            "valor_hora": to_decimal128(data.valor_hora),
        })
        await self.auditoria.registrar(admin, "crear", "tarifa", tarifa["_id"], admin["parqueadero_id"], despues={
            k: tarifa[k] for k in ("sede_id", "nombre", "tipo_vehiculo", "valor_hora")
        })
        return tarifa

    async def actualizar(self, admin: Document, tarifa_id: str, data: TarifaUpdate) -> Document:
        tid = parse_oid(tarifa_id)
        tarifa = await self.repository.get(tid, parqueadero_id=admin["parqueadero_id"])
        if not tarifa:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarifa no encontrada")
        cambios = clean(data.model_dump())
        if "valor_hora" in cambios:
            cambios["valor_hora"] = to_decimal128(cambios["valor_hora"])
        if not cambios:
            return tarifa
        actualizada = await self.repository.update(tid, cambios)
        await self.auditoria.registrar(admin, "actualizar", "tarifa", tid, admin["parqueadero_id"],
                                       **cambios_de(tarifa, cambios))
        return actualizada

    async def eliminar(self, admin: Document, tarifa_id: str) -> None:
        # Las reservas guardan una copia en `tarifa_aplicada`, así que borrar no afecta su cobro.
        tid = parse_oid(tarifa_id)
        tarifa = await self.repository.get(tid, parqueadero_id=admin["parqueadero_id"])
        if not tarifa or not await self.repository.delete(tid, parqueadero_id=admin["parqueadero_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarifa no encontrada")
        await self.auditoria.registrar(admin, "eliminar", "tarifa", tid, admin["parqueadero_id"], antes={
            k: tarifa[k] for k in ("sede_id", "nombre", "tipo_vehiculo", "valor_hora")
        })
