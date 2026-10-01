import math
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict
from zoneinfo import ZoneInfo

from bson import Decimal128, ObjectId
from fastapi import HTTPException, status

from app.core.config import settings

ZONA = ZoneInfo(settings.ZONA_HORARIA)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Las fechas sin zona horaria se asumen en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso no encontrado")
    return ObjectId(value)


def to_decimal128(value: Decimal) -> Decimal128:
    return Decimal128(value.quantize(Decimal("0.01")))


def clean(data: Dict[str, Any]) -> Dict[str, Any]:
    """Quita los None: los validadores de Mongo rechazan null en campos string."""
    return {k: v for k, v in data.items() if v is not None}


def punto(latitud: float, longitud: float) -> Dict[str, Any]:
    """GeoJSON Point (Mongo guarda [longitud, latitud])."""
    return {"type": "Point", "coordinates": [longitud, latitud]}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en línea recta entre dos coordenadas, en km."""
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def hoy_local() -> date:
    return utcnow().astimezone(ZONA).date()


def fecha_local(dt: datetime) -> date:
    return as_utc(dt).astimezone(ZONA).date()


def inicio_dia_utc(dia: date) -> datetime:
    """Medianoche (hora local) de `dia`, expresada en UTC para consultar Mongo."""
    return datetime.combine(dia, time.min, tzinfo=ZONA).astimezone(timezone.utc)


def formato_pesos(valor: Decimal) -> str:
    return "$" + f"{valor:,.0f}".replace(",", ".")


def formato_fecha_hora(dt: datetime) -> str:
    return as_utc(dt).astimezone(ZONA).strftime("%d/%m %I:%M %p")


def to_decimal(value: Any) -> Decimal:
    return value.to_decimal() if isinstance(value, Decimal128) else Decimal(value)
