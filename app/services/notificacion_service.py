from datetime import timedelta
from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.utils import clean, parse_oid, utcnow
from app.repositories.alerta_repository import AlertaRepository
from app.repositories.base import Document
from app.repositories.notificacion_repository import NotificacionRepository

# Para no llenar de avisos a quien sigue una sede muy movida.
PAUSA_ENTRE_ALERTAS = timedelta(minutes=10)


class NotificacionService:
    def __init__(self, repository: NotificacionRepository, alertas: AlertaRepository):
        self.repository = repository
        self.alertas = alertas

    async def notificar(
        self,
        usuario_id: ObjectId,
        titulo: str,
        mensaje: str,
        reserva_id: Optional[ObjectId] = None,
        sede_id: Optional[ObjectId] = None,
    ) -> Document:
        # TODO: enviar además push (Firebase Cloud Messaging) cuando la app registre su token.
        return await self.repository.insert(clean({
            "usuario_id": usuario_id,
            "titulo": titulo,
            "mensaje": mensaje,
            "leida": False,
            "fecha": utcnow(),
            "reserva_id": reserva_id,
            "sede_id": sede_id,
        }))

    async def listar(self, usuario: Document, solo_no_leidas: bool, skip: int, limit: int) -> List[Document]:
        filtro: Document = {"usuario_id": usuario["_id"]}
        if solo_no_leidas:
            filtro["leida"] = False
        return await self.repository.find(filtro, skip, limit, sort=[("fecha", -1)])

    async def no_leidas(self, usuario: Document) -> int:
        return await self.repository.count({"usuario_id": usuario["_id"], "leida": False})

    async def marcar_leida(self, usuario: Document, notificacion_id: str) -> Document:
        actualizada = await self.repository.update(parse_oid(notificacion_id), {"leida": True}, usuario_id=usuario["_id"])
        if not actualizada:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificación no encontrada")
        return actualizada

    async def marcar_todas_leidas(self, usuario: Document) -> None:
        await self.repository.collection.update_many({"usuario_id": usuario["_id"], "leida": False}, {"$set": {"leida": True}})

    async def cupo_liberado(self, sede: Document, espacio: Document) -> None:
        """Avisa a quienes tienen alerta en la sede (y tipo de espacio) que se liberó un cupo."""
        ahora = utcnow()
        alertas = await self.alertas.find({
            "sede_id": sede["_id"],
            "$and": [
                {"$or": [{"tipo": {"$exists": False}}, {"tipo": espacio["tipo"]}]},
                {"$or": [
                    {"ultima_notificacion": {"$exists": False}},
                    {"ultima_notificacion": {"$lt": ahora - PAUSA_ENTRE_ALERTAS}},
                ]},
            ],
        }, limit=0)
        for alerta in alertas:
            await self.notificar(
                alerta["usuario_id"],
                "¡Se liberó un cupo!",
                f"Hay un espacio {espacio['tipo']} libre en {sede['nombre']}.",
                sede_id=sede["_id"],
            )
            await self.alertas.update(alerta["_id"], {"ultima_notificacion": ahora})
