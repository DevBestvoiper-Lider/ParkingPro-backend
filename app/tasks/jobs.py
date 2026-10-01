"""Tareas que corren cada minuto dentro de la API (una sola vez por proceso).

Son idempotentes: cada cambio es una actualización condicional, así que si varios procesos
las ejecutan a la vez no se duplican efectos.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId

from app.core.config import settings
from app.core.realtime import HubTiempoReal
from app.core.utils import utcnow
from app.models.collections import RESERVAS, SUSCRIPCIONES
from app.repositories.actividad_repository import ActividadRepository
from app.repositories.alerta_repository import AlertaRepository
from app.repositories.notificacion_repository import NotificacionRepository
from app.repositories.suscripcion_repository import SuscripcionRepository
from app.services.eventos import Eventos
from app.services.notificacion_service import NotificacionService
from app.services.suscripcion_service import DURACION_PLAN

logger = logging.getLogger(__name__)
INTERVALO_SEGUNDOS = 60


async def vencer_reservas_pendientes(db, hub: HubTiempoReal, ahora: Optional[datetime] = None) -> int:
    """Cancela las reservas pendientes sin ningún pago cuyo plazo para pagar ya pasó."""
    ahora = ahora or utcnow()
    # El _id de Mongo guarda la fecha de creación: sirve como "creada_en".
    limite = ObjectId.from_datetime(ahora - timedelta(minutes=settings.RESERVA_PENDIENTE_MINUTOS))
    limite_afiliado = ahora - timedelta(minutes=settings.RESERVA_PENDIENTE_MINUTOS_AFILIADO)
    candidatas = await db[RESERVAS].find(
        {"estado": "pendiente", "pagos": {"$size": 0}, "_id": {"$lt": limite}}
    ).to_list(length=None)

    suscripciones = SuscripcionRepository(db)
    eventos = Eventos(ActividadRepository(db), hub)
    notificaciones = NotificacionService(NotificacionRepository(db), AlertaRepository(db))
    vencidas = 0
    for reserva in candidatas:
        if reserva["_id"].generation_time > limite_afiliado and await suscripciones.vigente(reserva["usuario_id"]):
            continue  # los afiliados tienen más tiempo para pagar
        resultado = await db[RESERVAS].update_one(
            {"_id": reserva["_id"], "estado": "pendiente", "pagos": {"$size": 0}},
            {"$set": {"estado": "cancelada"}},
        )
        if not resultado.modified_count:
            continue
        vencidas += 1
        await eventos.registrar(
            reserva["parqueadero_id"], reserva["sede_id"], "reserva_vencida",
            f"{reserva.get('codigo', '')} vencida por falta de pago",
            reserva_id=reserva["_id"], espacio_id=reserva["espacio_id"],
        )
        await notificaciones.notificar(
            reserva["usuario_id"], "Reserva vencida",
            f"Tu reserva {reserva.get('codigo', '')} se canceló porque no se pagó a tiempo.",
            reserva_id=reserva["_id"],
        )
    return vencidas


async def vencer_suscripciones(db, ahora: Optional[datetime] = None) -> int:
    """Renueva las que tienen renovación automática y marca como vencidas las demás."""
    ahora = ahora or utcnow()
    coleccion = db[SUSCRIPCIONES]
    cambios = 0
    for suscripcion in await coleccion.find(
        {"estado": {"$in": ["activa", "cancelada"]}, "fecha_fin": {"$lte": ahora}}
    ).to_list(length=None):
        if suscripcion["estado"] == "activa" and suscripcion.get("renovacion_automatica"):
            # TODO: cobrar la renovación con la pasarela de pagos.
            nuevo_fin = suscripcion["fecha_fin"] + DURACION_PLAN
            filtro_set = {"fecha_fin": nuevo_fin}
        else:
            filtro_set = {"estado": "vencida"}
        resultado = await coleccion.update_one(
            {"_id": suscripcion["_id"], "fecha_fin": suscripcion["fecha_fin"]}, {"$set": filtro_set}
        )
        cambios += resultado.modified_count
    return cambios


async def correr_tareas(db, hub: HubTiempoReal) -> None:
    vencidas = await vencer_reservas_pendientes(db, hub)
    suscripciones = await vencer_suscripciones(db)
    if vencidas or suscripciones:
        logger.info("Tareas: %s reservas vencidas, %s suscripciones actualizadas", vencidas, suscripciones)


async def ejecutar_periodicamente(db, hub: HubTiempoReal) -> None:
    while True:
        try:
            await correr_tareas(db, hub)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falló una tarea periódica")
        await asyncio.sleep(INTERVALO_SEGUNDOS)
