from typing import Optional

from bson import ObjectId

from app.core.utils import utcnow
from app.models.collections import SUSCRIPCIONES
from app.repositories.base import BaseRepository, Document


class SuscripcionRepository(BaseRepository):
    collection_name = SUSCRIPCIONES

    async def vigente(self, usuario_id: ObjectId) -> Optional[Document]:
        """Suscripción que da beneficios hoy (una cancelada sigue vigente hasta su fecha_fin)."""
        return await self.collection.find_one(
            {"usuario_id": usuario_id, "estado": {"$in": ["activa", "cancelada"]}, "fecha_fin": {"$gt": utcnow()}},
            sort=[("fecha_fin", -1)],
        )
