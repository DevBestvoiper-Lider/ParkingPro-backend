from typing import Optional, Tuple

from bson import ObjectId
from pymongo import ReturnDocument

from app.models.collections import PARQUEADEROS
from app.repositories.base import BaseRepository, Document


class ParqueaderoRepository(BaseRepository):
    collection_name = PARQUEADEROS

    async def get_sede(self, sede_id: ObjectId) -> Optional[Tuple[Document, Document]]:
        """Devuelve (parqueadero, sede) a partir del _id de la sede embebida."""
        parqueadero = await self.collection.find_one({"sedes._id": sede_id})
        if not parqueadero:
            return None
        sede = next(s for s in parqueadero["sedes"] if s["_id"] == sede_id)
        return parqueadero, sede

    async def add_sede(self, parqueadero_id: ObjectId, sede: Document) -> Optional[Document]:
        return await self.collection.find_one_and_update(
            {"_id": parqueadero_id},
            {"$push": {"sedes": sede}},
            return_document=ReturnDocument.AFTER,
        )

    async def update_sede(self, parqueadero_id: ObjectId, sede_id: ObjectId, cambios: Document) -> Optional[Document]:
        return await self.collection.find_one_and_update(
            {"_id": parqueadero_id, "sedes._id": sede_id},
            {"$set": {f"sedes.$.{campo}": valor for campo, valor in cambios.items()}},
            return_document=ReturnDocument.AFTER,
        )
