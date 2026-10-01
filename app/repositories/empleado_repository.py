from typing import Optional

from app.models.collections import EMPLEADOS
from app.repositories.base import BaseRepository, Document


class EmpleadoRepository(BaseRepository):
    collection_name = EMPLEADOS

    async def get_by_email(self, email: str) -> Optional[Document]:
        return await self.collection.find_one({"email": email.lower()})
