from app.models.collections import ALERTAS_CUPO
from app.repositories.base import BaseRepository


class AlertaRepository(BaseRepository):
    collection_name = ALERTAS_CUPO
