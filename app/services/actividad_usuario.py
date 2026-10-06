"""Mi actividad: se calcula con las reservas que ya existen. No hay colección nueva."""
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.billing import calcular_total
from app.core.config import settings
from app.core.utils import as_utc, fecha_local, hoy_local, to_decimal, utcnow
from app.repositories.base import Document

MESES_ACTIVIDAD = 6
_CENTAVOS = Decimal("0.01")


def meses_recientes(hoy: Optional[date] = None, n: int = MESES_ACTIVIDAD) -> List[str]:
    """Los últimos `n` meses calendario (hora de Colombia), del más antiguo al actual."""
    dia = hoy or hoy_local()
    año, mes = dia.year, dia.month
    claves: List[str] = []
    for _ in range(n):
        claves.append(f"{año:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes, año = 12, año - 1
    return list(reversed(claves))


def _total_cobrado(reserva: Document) -> Decimal:
    if reserva.get("estado") == "cancelada":
        return Decimal("0.00")
    valor = to_decimal(reserva["tarifa_aplicada"]["valor_hora"])
    sesion = reserva.get("sesion") or {}
    if sesion.get("hora_entrada"):
        return calcular_total(valor, sesion["hora_entrada"], sesion.get("hora_salida") or utcnow())
    return calcular_total(valor, reserva["fecha_inicio"], reserva["fecha_fin"])


def _horas_sesion(reserva: Document) -> Decimal:
    sesion = reserva.get("sesion") or {}
    entrada = sesion.get("hora_entrada")
    if not entrada:
        return Decimal(0)
    salida = sesion.get("hora_salida") or utcnow()
    segundos = max((as_utc(salida) - as_utc(entrada)).total_seconds(), 0)
    return Decimal(str(segundos)) / Decimal(3600)


def _top(items: Dict[str, dict]) -> List[dict]:
    return sorted(items.values(), key=lambda item: (-item["visitas"], item["nombre"]))[:3]


def calcular_actividad(reservas: List[Document]) -> dict:
    """Consumo del usuario a partir de sus reservas ya enriquecidas (sede y placa)."""
    cero = Decimal("0.00")
    meses = meses_recientes()
    gasto = {mes: cero for mes in meses}
    total_gastado = cero
    horas = Decimal(0)
    completadas = 0
    canceladas = 0
    sedes: Dict[str, dict] = {}
    vehiculos: Dict[str, dict] = {}
    suma_visitas = cero
    ahorro_real = cero
    ahorro_estimado = cero
    hubo_descuento = False

    for reserva in reservas:
        estado = reserva.get("estado")
        if estado == "cancelada":
            canceladas += 1
        elif estado == "completada":
            completadas += 1

        for pago in reserva.get("pagos") or []:
            if pago.get("estado") == "pagado":
                monto = to_decimal(pago["monto"])
            elif pago.get("estado") == "reembolsado":
                monto = -to_decimal(pago["monto"])
            else:
                continue
            total_gastado += monto
            mes = fecha_local(pago["fecha_pago"]).strftime("%Y-%m")
            if mes in gasto:
                gasto[mes] += monto

        horas += _horas_sesion(reserva)
        if estado != "completada":
            continue

        cobrado = _total_cobrado(reserva)
        suma_visitas += cobrado
        pct = int((reserva.get("tarifa_aplicada") or {}).get("descuento_pct") or 0)
        if pct and pct < 100:
            hubo_descuento = True
            ahorro_real += cobrado * Decimal(pct) / Decimal(100 - pct)
        else:
            ahorro_estimado += cobrado * Decimal(settings.AFILIADO_DESCUENTO_PCT) / Decimal(100)

        sede_id = str(reserva["sede_id"])
        sede = sedes.setdefault(sede_id, {
            "id": sede_id, "nombre": reserva.get("sede_nombre") or "Sede", "visitas": 0,
        })
        sede["visitas"] += 1
        vehiculo_id = str(reserva["vehiculo_id"])
        vehiculo = vehiculos.setdefault(vehiculo_id, {
            "id": vehiculo_id, "nombre": reserva.get("placa") or "Vehículo", "visitas": 0,
        })
        vehiculo["visitas"] += 1

    anterior, actual = gasto[meses[-2]], gasto[meses[-1]]
    tendencia: Optional[float] = None
    if anterior > 0:
        tendencia = round(float((actual - anterior) / anterior * 100), 1)

    return {
        "total_gastado": total_gastado.quantize(_CENTAVOS),
        "gasto_por_mes": [{"mes": mes, "total": gasto[mes].quantize(_CENTAVOS)} for mes in meses],
        "tendencia_pct": tendencia,
        "horas_estacionado": round(float(horas), 2),
        "reservas_completadas": completadas,
        "reservas_canceladas": canceladas,
        "sedes_mas_usadas": _top(sedes),
        "vehiculos_mas_usados": _top(vehiculos),
        "promedio_por_visita": (suma_visitas / completadas).quantize(_CENTAVOS) if completadas else cero,
        "ahorro_afiliado": (ahorro_real if hubo_descuento else ahorro_estimado).quantize(_CENTAVOS),
        "ahorro_es_estimado": not hubo_descuento,
    }
