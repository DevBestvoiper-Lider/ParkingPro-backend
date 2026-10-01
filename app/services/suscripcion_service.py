from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.utils import parse_oid, to_decimal128, utcnow
from app.repositories.alerta_repository import AlertaRepository
from app.repositories.base import Document
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.suscripcion_repository import SuscripcionRepository
from app.schemas.suscripcion import AlertaCreate, SuscripcionCreate

DURACION_PLAN = timedelta(days=30)


def planes() -> List[Document]:
    return [
        {
            "plan": "por_uso",
            "nombre": "Plan por uso",
            "precio_mensual": Decimal("0"),
            "descuento_pct": 0,
            "beneficios": ["Tarifa estándar por cada parqueo", "Sin costo fijo mensual"],
            "recomendado_para": "Uso ocasional",
        },
        {
            "plan": "afiliado",
            "nombre": "Plan Afiliado",
            "precio_mensual": Decimal(settings.AFILIADO_PRECIO_MENSUAL),
            "descuento_pct": settings.AFILIADO_DESCUENTO_PCT,
            "beneficios": [
                f"{settings.AFILIADO_DESCUENTO_PCT}% de descuento en cada parqueo",
                "Prioridad de reserva en horas pico",
                f"{settings.RESERVA_PENDIENTE_MINUTOS_AFILIADO} min para pagar una reserva (vs {settings.RESERVA_PENDIENTE_MINUTOS})",
                "Alertas cuando se libera un cupo",
                "Soporte prioritario",
            ],
            "recomendado_para": "Uso frecuente",
        },
    ]


class SuscripcionService:
    def __init__(self, repository: SuscripcionRepository, alertas: AlertaRepository, parqueaderos: ParqueaderoRepository):
        self.repository = repository
        self.alertas = alertas
        self.parqueaderos = parqueaderos

    async def vigente(self, usuario: Document) -> Optional[Document]:
        return await self.repository.vigente(usuario["_id"])

    async def suscribir(self, usuario: Document, data: SuscripcionCreate) -> Document:
        if await self.repository.vigente(usuario["_id"]):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes una suscripción vigente")
        # TODO: cobrar con la pasarela de pagos; por ahora el cobro se da por aprobado.
        inicio = utcnow()
        return await self.repository.insert({
            "usuario_id": usuario["_id"],
            "plan": "afiliado",
            "precio": to_decimal128(Decimal(settings.AFILIADO_PRECIO_MENSUAL)),
            "descuento_pct": settings.AFILIADO_DESCUENTO_PCT,
            "fecha_inicio": inicio,
            "fecha_fin": inicio + DURACION_PLAN,
            "estado": "activa",
            "renovacion_automatica": data.renovacion_automatica,
            "metodo_pago": data.metodo_pago,
        })

    async def cancelar(self, usuario: Document) -> Document:
        """Deja de renovarse; los beneficios siguen hasta fecha_fin."""
        suscripcion = await self.repository.vigente(usuario["_id"])
        if not suscripcion or suscripcion["estado"] != "activa":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No tienes una suscripción activa")
        return await self.repository.update(suscripcion["_id"], {"estado": "cancelada", "renovacion_automatica": False})

    # ---------- Alertas de cupo (beneficio Afiliado) ----------

    async def crear_alerta(self, usuario: Document, data: AlertaCreate) -> Document:
        if not await self.repository.vigente(usuario["_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Las alertas de cupo son un beneficio del plan Afiliado")
        sede_id = parse_oid(data.sede_id)
        if not await self.parqueaderos.get_sede(sede_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        if await self.alertas.exists({"usuario_id": usuario["_id"], "sede_id": sede_id}):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes una alerta en esa sede")
        doc = {"usuario_id": usuario["_id"], "sede_id": sede_id, "fecha_creacion": utcnow()}
        if data.tipo:
            doc["tipo"] = data.tipo
        return await self.alertas.insert(doc)

    async def listar_alertas(self, usuario: Document) -> List[Document]:
        return await self.alertas.find({"usuario_id": usuario["_id"]}, limit=0, sort=[("fecha_creacion", -1)])

    async def eliminar_alerta(self, usuario: Document, alerta_id: str) -> None:
        if not await self.alertas.delete(parse_oid(alerta_id), usuario_id=usuario["_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
