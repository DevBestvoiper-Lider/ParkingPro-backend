"""Comisión de ParkingPro y compensación del descuento Afiliado en cada pago."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.utils import as_utc

CENTAVO = Decimal("0.01")


def condiciones_socio() -> Dict[str, Any]:
    """Lo pactado con un socio nuevo (copia de la política vigente)."""
    return {
        "comision_pct": settings.COMISION_PCT,
        "limite_deuda": settings.LIMITE_DEUDA,
        "dias_gracia": settings.DEUDA_DIAS_GRACIA,
        "politica": "defecto",
    }


def condiciones_parqueadero(creado: datetime) -> Dict[str, Any]:
    """Prueba y comisión en prueba de un parqueadero nuevo, aunque el socio sea antiguo."""
    return {
        "comision_prueba_pct": settings.COMISION_PRUEBA_PCT,
        "prueba_hasta": creado + timedelta(days=settings.PRUEBA_DIAS),
        "politica": "defecto",
    }


def comision_pct(socio: Optional[Dict[str, Any]], parqueadero: Dict[str, Any], fecha: datetime) -> int:
    """La comisión que aplica a un pago en `fecha`: la de prueba si el parqueadero sigue en prueba."""
    condiciones = parqueadero.get("condiciones") or {}
    prueba_hasta = condiciones.get("prueba_hasta")
    if prueba_hasta is not None and as_utc(fecha) < as_utc(prueba_hasta):
        return int(condiciones.get("comision_prueba_pct", 0))
    return int(((socio or {}).get("condiciones") or {}).get("comision_pct", 0))


def montos_de_pago(monto: Decimal, pct: int, descuento_pct: int) -> Tuple[Decimal, Decimal]:
    """(comisión sobre lo que paga el cliente, compensación del descuento que asume ParkingPro).

    Con el descuento, el cliente paga `monto` = tarifa × (100 − d) %. La compensación completa la
    tarifa para el socio: tarifa − monto = monto × d / (100 − d).
    """
    comision = (monto * pct / 100).quantize(CENTAVO)
    compensacion = Decimal("0.00")
    if 0 < descuento_pct < 100:
        compensacion = (monto * descuento_pct / (100 - descuento_pct)).quantize(CENTAVO)
    return comision, compensacion
