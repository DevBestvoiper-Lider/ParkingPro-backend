from datetime import datetime
from typing import List, Optional, Set

from bson import ObjectId
from pymongo import ReturnDocument

from app.models.collections import RESERVAS
from app.repositories.base import BaseRepository, Document

ESTADOS_ACTIVOS = ["pendiente", "confirmada"]


class ReservaRepository(BaseRepository):
    collection_name = RESERVAS

    async def espacios_reservados(self, espacio_ids: List[ObjectId], inicio: datetime, fin: datetime) -> Set[ObjectId]:
        """Espacios con alguna reserva activa que se cruza con [inicio, fin)."""
        if not espacio_ids:
            return set()
        cursor = self.collection.find(
            {
                "espacio_id": {"$in": espacio_ids},
                "estado": {"$in": ESTADOS_ACTIVOS},
                "fecha_inicio": {"$lt": fin},
                "fecha_fin": {"$gt": inicio},
            },
            {"espacio_id": 1},
        )
        return {doc["espacio_id"] for doc in await cursor.to_list(length=None)}

    async def add_pago(self, reserva_id: ObjectId, pago: Document) -> Optional[Document]:
        return await self.collection.find_one_and_update(
            {"_id": reserva_id},
            {"$push": {"pagos": pago}},
            return_document=ReturnDocument.AFTER,
        )
