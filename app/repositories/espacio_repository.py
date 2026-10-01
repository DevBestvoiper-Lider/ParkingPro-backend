from bson import ObjectId

from app.models.collections import ESPACIOS
from app.repositories.base import BaseRepository


class EspacioRepository(BaseRepository):
    collection_name = ESPACIOS

    async def ocupar(self, espacio_id: ObjectId) -> bool:
        """Pasa el espacio a 'ocupado' solo si estaba 'disponible' (atómico)."""
        return await self.update(espacio_id, {"estado": "ocupado"}, estado="disponible") is not None

    async def liberar(self, espacio_id: ObjectId) -> None:
        await self.update(espacio_id, {"estado": "disponible"}, estado="ocupado")
