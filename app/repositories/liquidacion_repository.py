from typing import Optional

from bson import ObjectId

from app.models.collections import LIQUIDACIONES
from app.repositories.base import BaseRepository, Document


class LiquidacionRepository(BaseRepository):
    collection_name = LIQUIDACIONES

    async def ultima(self, socio_id: ObjectId) -> Optional[Document]:
        return await self.collection.find_one({"socio_id": socio_id}, sort=[("semana_inicio", -1)])

    async def guardar(self, doc: Document) -> Document:
        """Idempotente: si otro proceso ya generó esa semana, devuelve la existente."""
        await self.collection.update_one(
            {"socio_id": doc["socio_id"], "semana_inicio": doc["semana_inicio"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        return await self.collection.find_one({"socio_id": doc["socio_id"], "semana_inicio": doc["semana_inicio"]})
