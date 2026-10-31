from typing import Optional

from app.models.collections import SOCIOS
from app.repositories.base import BaseRepository, Document


class SocioRepository(BaseRepository):
    collection_name = SOCIOS

    async def get_by_email(self, email: str) -> Optional[Document]:
        return await self.collection.find_one({"email": email.lower()})
