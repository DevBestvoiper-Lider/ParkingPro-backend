from pymongo import ReturnDocument

from app.models.collections import CONTADORES


class ContadorRepository:
    def __init__(self, db):
        self.collection = db[CONTADORES]

    async def siguiente(self, nombre: str) -> int:
        """Incrementa y devuelve la secuencia `nombre` de forma atómica."""
        doc = await self.collection.find_one_and_update(
            {"_id": nombre},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["seq"]
