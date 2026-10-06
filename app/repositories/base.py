from typing import Any, Dict, List, Optional, Sequence, Tuple

from bson import ObjectId
from pymongo import ReturnDocument

Document = Dict[str, Any]


class BaseRepository:
    collection_name: str

    def __init__(self, db):
        self.collection = db[self.collection_name]

    async def get(self, doc_id: ObjectId, **filtros: Any) -> Optional[Document]:
        return await self.collection.find_one({"_id": doc_id, **filtros})

    async def find(
        self,
        filtro: Document,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[Sequence[Tuple[str, int]]] = None,
    ) -> List[Document]:
        """`limit=0` devuelve todos los resultados."""
        cursor = self.collection.find(filtro)
        if sort:
            cursor = cursor.sort(list(sort))
        return await cursor.skip(skip).limit(limit).to_list(length=None)

    async def count(self, filtro: Document) -> int:
        return await self.collection.count_documents(filtro)

    async def exists(self, filtro: Document) -> bool:
        return await self.collection.find_one(filtro, {"_id": 1}) is not None

    async def insert(self, doc: Document) -> Document:
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def update(
        self,
        doc_id: ObjectId,
        cambios: Document,
        unset: Optional[Sequence[str]] = None,
        **condiciones: Any,
    ) -> Optional[Document]:
        """$set atómico. `unset` borra campos. None si el documento no existe o no cumple `condiciones`."""
        operacion: Document = {}
        if cambios:
            operacion["$set"] = cambios
        if unset:
            operacion["$unset"] = {campo: "" for campo in unset}
        return await self.collection.find_one_and_update(
            {"_id": doc_id, **condiciones},
            operacion,
            return_document=ReturnDocument.AFTER,
        )

    async def delete(self, doc_id: ObjectId, **filtros: Any) -> bool:
        result = await self.collection.delete_one({"_id": doc_id, **filtros})
        return result.deleted_count == 1
