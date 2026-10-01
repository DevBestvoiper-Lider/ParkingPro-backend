from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.models.collections import USUARIOS
from app.repositories.base import BaseRepository, Document


class UsuarioRepository(BaseRepository):
    collection_name = USUARIOS

    async def get_by_email(self, email: str) -> Optional[Document]:
        return await self.collection.find_one({"email": email.lower()})

    async def add_vehiculo(self, usuario_id: ObjectId, vehiculo: Document) -> Optional[Document]:
        return await self.collection.find_one_and_update(
            {"_id": usuario_id},
            {"$push": {"vehiculos": vehiculo}},
            return_document=ReturnDocument.AFTER,
        )

    async def remove_vehiculo(self, usuario_id: ObjectId, vehiculo_id: ObjectId) -> Optional[Document]:
        return await self.collection.find_one_and_update(
            {"_id": usuario_id, "vehiculos._id": vehiculo_id},
            {"$pull": {"vehiculos": {"_id": vehiculo_id}}},
            return_document=ReturnDocument.AFTER,
        )
