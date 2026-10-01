from typing import Optional

from bson import ObjectId

from app.core.realtime import HubTiempoReal
from app.core.utils import utcnow
from app.repositories.actividad_repository import ActividadRepository


class Eventos:
    """Registra la actividad del parqueadero (panel web) y la avisa en tiempo real a la sede."""

    def __init__(self, actividad: ActividadRepository, hub: HubTiempoReal):
        self.actividad = actividad
        self.hub = hub

    async def registrar(
        self,
        parqueadero_id: ObjectId,
        sede_id: ObjectId,
        tipo: str,
        descripcion: str,
        reserva_id: Optional[ObjectId] = None,
        espacio_id: Optional[ObjectId] = None,
        estado_espacio: Optional[str] = None,
    ) -> None:
        fecha = utcnow()
        doc = {"parqueadero_id": parqueadero_id, "sede_id": sede_id, "tipo": tipo, "descripcion": descripcion, "fecha": fecha}
        if reserva_id:
            doc["reserva_id"] = reserva_id
        if espacio_id:
            doc["espacio_id"] = espacio_id
        await self.actividad.insert(doc)
        await self.hub.publicar(str(sede_id), {
            "evento": tipo,
            "descripcion": descripcion,
            "reserva_id": reserva_id and str(reserva_id),
            "espacio_id": espacio_id and str(espacio_id),
            "estado_espacio": estado_espacio,
            "fecha": fecha.isoformat(),
        })
