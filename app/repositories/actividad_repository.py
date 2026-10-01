from app.models.collections import ACTIVIDAD
from app.repositories.base import BaseRepository


class ActividadRepository(BaseRepository):
    collection_name = ACTIVIDAD
