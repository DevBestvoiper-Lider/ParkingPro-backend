from typing import List

from app.repositories.base import Document
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.socio_repository import SocioRepository


class SocioService:
    def __init__(self, repository: SocioRepository, parqueaderos: ParqueaderoRepository):
        self.repository = repository
        self.parqueaderos = parqueaderos

    async def portafolio(self, socio: Document) -> List[Document]:
        """Todos los parqueaderos del socio, incluidos los suspendidos."""
        return await self.parqueaderos.find({"socio_id": socio["_id"]}, limit=0, sort=[("nombre", 1)])
