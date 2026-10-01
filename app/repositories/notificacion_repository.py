from app.models.collections import NOTIFICACIONES
from app.repositories.base import BaseRepository


class NotificacionRepository(BaseRepository):
    collection_name = NOTIFICACIONES
