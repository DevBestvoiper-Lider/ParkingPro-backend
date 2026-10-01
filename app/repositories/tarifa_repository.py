from app.models.collections import TARIFAS
from app.repositories.base import BaseRepository


class TarifaRepository(BaseRepository):
    collection_name = TARIFAS
