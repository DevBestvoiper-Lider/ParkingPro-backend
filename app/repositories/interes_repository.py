from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bson import ObjectId

from app.core.utils import utcnow
from app.models.collections import INTERESADOS
from app.repositories.base import BaseRepository

DURACION_INTERES = timedelta(minutes=2)


class InteresRepository(BaseRepository):
    collection_name = INTERESADOS

    async def marcar(self, sede_id: ObjectId, clave: str, espacio_id: Optional[ObjectId]) -> None:
        """Registra (o renueva) que `clave` está viendo la sede; caduca en DURACION_INTERES."""
        await self.collection.update_one(
            {"_id": f"{sede_id}:{clave}"},
            {"$set": {"sede_id": sede_id, "espacio_id": espacio_id, "expira": utcnow() + DURACION_INTERES}},
            upsert=True,
        )

    async def vigentes(self, sede_ids: List[ObjectId], ahora: Optional[datetime] = None) -> List[dict]:
        # El índice TTL borra con hasta ~60 s de retraso: filtramos por `expira` igual.
        return await self.collection.find(
            {"sede_id": {"$in": sede_ids}, "expira": {"$gt": ahora or utcnow()}}
        ).to_list(length=None)

    async def por_sede(self, sede_ids: List[ObjectId]) -> Dict[ObjectId, int]:
        conteo: Dict[ObjectId, int] = {}
        for doc in await self.vigentes(sede_ids):
            conteo[doc["sede_id"]] = conteo.get(doc["sede_id"], 0) + 1
        return conteo
