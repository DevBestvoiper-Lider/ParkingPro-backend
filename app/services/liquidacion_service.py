"""Liquidación semanal con cada socio y control del límite de deuda.

Por cada pago:
- App: ParkingPro recibe el dinero y le debe al socio el monto menos la comisión.
- Caja: el socio recibe el dinero y le debe a ParkingPro la comisión.
- Afiliado: ParkingPro le paga al socio la compensación del descuento, sin importar el método.
- Reembolso: ParkingPro conserva la comisión; en app devuelve el dinero al cliente y lo descuenta
  al socio; en cualquier método se revierte la compensación.

total = pagos_app + compensacion − comision_app − comision_caja − reembolsos_app + saldo_anterior
Positivo: ParkingPro transfiere al socio. Negativo: el socio debe.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from bson import Decimal128

from app.core.utils import as_utc, fecha_local, formato_pesos, inicio_dia_utc, to_decimal, to_decimal128, utcnow
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.base import Document
from app.repositories.liquidacion_repository import LiquidacionRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.reserva_repository import ReservaRepository
from app.repositories.socio_repository import SocioRepository
from app.tasks.background import send_aviso_deuda_email

CONCEPTOS = ("pagos_app", "compensacion", "comision_app", "comision_caja", "reembolsos_app")
CERO = Decimal("0.00")
SISTEMA = {"cuenta": "sistema", "nombre": "ParkingPro"}


def inicio_semana(dt: datetime) -> datetime:
    """Lunes 00:00 (hora de Colombia) de la semana de `dt`, en UTC."""
    dia = fecha_local(dt)
    return inicio_dia_utc(dia - timedelta(days=dia.weekday()))


def fin_semana(inicio: datetime) -> datetime:
    return inicio_dia_utc(fecha_local(inicio) + timedelta(days=7))


def total_de(conceptos: Dict[str, Decimal], saldo_anterior: Decimal) -> Decimal:
    return (
        conceptos["pagos_app"] + conceptos["compensacion"] - conceptos["comision_app"]
        - conceptos["comision_caja"] - conceptos["reembolsos_app"] + saldo_anterior
    )


class LiquidacionService:
    def __init__(
        self,
        repository: LiquidacionRepository,
        socios: SocioRepository,
        parqueaderos: ParqueaderoRepository,
        reservas: ReservaRepository,
        auditoria: AuditoriaRepository,
    ):
        self.repository = repository
        self.socios = socios
        self.parqueaderos = parqueaderos
        self.reservas = reservas
        self.auditoria = auditoria

    @classmethod
    def de(cls, db) -> "LiquidacionService":
        return cls(
            LiquidacionRepository(db), SocioRepository(db), ParqueaderoRepository(db),
            ReservaRepository(db), AuditoriaRepository(db),
        )

    async def correr(self, ahora: Optional[datetime] = None) -> None:
        """Tarea periódica: liquida las semanas cerradas y revisa la deuda de cada socio activo."""
        for socio in await self.socios.find({"estado": "activo"}, limit=0):
            await self.revisar_deuda(socio, ahora)

    # ---------- Consultas del socio ----------

    async def listar(self, socio: Document, skip: int, limit: int) -> List[Document]:
        await self.generar(socio)
        return await self.repository.find({"socio_id": socio["_id"]}, skip, limit, sort=[("semana_inicio", -1)])

    async def estado_de_cuenta(self, socio: Document, ahora: Optional[datetime] = None) -> Document:
        """Lo que va desde la última liquidación hasta ahora, más el saldo que viene arrastrando."""
        ahora = ahora or utcnow()
        await self.generar(socio, ahora)
        ultima = await self.repository.ultima(socio["_id"])
        desde = as_utc(ultima["semana_fin"]) if ultima else _liquida_desde(socio)
        conceptos = await self.calcular(socio, desde, ahora)
        saldo_anterior = _saldo_pendiente(ultima)
        total = total_de(conceptos, saldo_anterior)
        condiciones = socio.get("condiciones") or {}
        limite = Decimal(condiciones.get("limite_deuda", 0))
        deuda = max(-total, CERO)
        return {
            "desde": desde,
            "hasta": ahora,
            **conceptos,
            "saldo_anterior": saldo_anterior,
            "total": total,
            "deuda": deuda,
            "limite_deuda": limite,
            "uso_limite_pct": _uso_pct(deuda, limite),
            "comision_pct": int(condiciones.get("comision_pct", 0)),
            "excedida_desde": (socio.get("deuda") or {}).get("excedida_desde"),
        }

    # ---------- Cálculo ----------

    async def calcular(self, socio: Document, desde: datetime, hasta: datetime) -> Dict[str, Decimal]:
        conceptos = {k: CERO for k in CONCEPTOS}
        pids = [p["_id"] for p in await self.parqueaderos.find({"socio_id": socio["_id"]}, limit=0)]
        if not pids or desde >= hasta:
            return conceptos
        reservas = await self.reservas.find({
            "parqueadero_id": {"$in": pids},
            "pagos": {"$elemMatch": {"fecha_pago": {"$gte": desde, "$lt": hasta}}},
        }, limit=0)
        for reserva in reservas:
            for pago in reserva.get("pagos", []):
                if not desde <= as_utc(pago["fecha_pago"]) < hasta:
                    continue
                monto = to_decimal(pago["monto"])
                comision = _decimal(pago.get("comision"))
                compensacion = _decimal(pago.get("compensacion"))
                app = pago["metodo_pago"] == "app"
                if pago["estado"] == "pagado":
                    if app:
                        conceptos["pagos_app"] += monto
                        conceptos["comision_app"] += comision
                    else:
                        conceptos["comision_caja"] += comision
                    conceptos["compensacion"] += compensacion
                elif pago["estado"] == "reembolsado":
                    if app:
                        conceptos["reembolsos_app"] += monto
                    conceptos["compensacion"] -= compensacion
        return conceptos

    async def generar(self, socio: Document, ahora: Optional[datetime] = None) -> int:
        """Genera las semanas cerradas que falten (lunes a domingo). Idempotente."""
        ahora = ahora or utcnow()
        liquida_desde = _liquida_desde(socio)
        ultima = await self.repository.ultima(socio["_id"])
        inicio = as_utc(ultima["semana_fin"]) if ultima else inicio_semana(liquida_desde)
        generadas = 0
        while fin_semana(inicio) <= ahora:
            fin = fin_semana(inicio)
            conceptos = await self.calcular(socio, max(inicio, liquida_desde), fin)
            saldo_anterior = _saldo_pendiente(ultima)
            nueva = await self.repository.guardar({
                "socio_id": socio["_id"],
                "semana_inicio": inicio,
                "semana_fin": fin,
                **{k: to_decimal128(v) for k, v in conceptos.items()},
                "saldo_anterior": to_decimal128(saldo_anterior),
                "total": to_decimal128(total_de(conceptos, saldo_anterior)),
                "estado": "pendiente",
                "fecha_generada": ahora,
            })
            if ultima and ultima["estado"] == "pendiente":
                # Su saldo pasó a la nueva; no se paga dos veces.
                await self.repository.update(ultima["_id"], {"estado": "trasladada"}, estado="pendiente")
            ultima = nueva
            inicio = fin
            generadas += 1
        return generadas

    # ---------- Límite de deuda ----------

    async def revisar_deuda(self, socio: Document, ahora: Optional[datetime] = None) -> None:
        """Avisa al 80 % y al 100 %; pasada la gracia suspende sus parqueaderos; al bajar los reactiva."""
        if not socio.get("condiciones"):
            return  # sin nada pactado (no migrado) no hay límite que aplicar
        ahora = ahora or utcnow()
        cuenta = await self.estado_de_cuenta(socio, ahora)
        uso = cuenta["uso_limite_pct"]
        estado = socio.get("deuda") or {}
        cambios: Document = {}
        quitar: List[str] = []

        aviso = 100 if uso >= 100 else 80 if uso >= 80 else None
        if aviso is None:
            if "aviso_pct" in estado:
                quitar.append("deuda.aviso_pct")
        elif aviso != estado.get("aviso_pct"):
            cambios["deuda.aviso_pct"] = aviso
            await send_aviso_deuda_email(
                socio["email"], socio["nombre"], aviso,
                formato_pesos(cuenta["deuda"]), formato_pesos(cuenta["limite_deuda"]),
            )

        if uso >= 100:
            excedida = estado.get("excedida_desde")
            if excedida is None:
                excedida = ahora
                cambios["deuda.excedida_desde"] = ahora
            dias = int((socio.get("condiciones") or {}).get("dias_gracia", 0))
            if ahora - as_utc(excedida) >= timedelta(days=dias):
                await self._suspender(socio, ahora)
        else:
            if "excedida_desde" in estado:
                quitar.append("deuda.excedida_desde")
            await self._reactivar(socio)

        if cambios or quitar:
            await self.socios.update(socio["_id"], cambios, unset=quitar)

    async def _suspender(self, socio: Document, ahora: datetime) -> None:
        for parqueadero in await self.parqueaderos.find(
            {"socio_id": socio["_id"], "estado": {"$in": ["activo", "en_prueba"]}}, limit=0
        ):
            antes = parqueadero["estado"]
            hecho = await self.parqueaderos.update(parqueadero["_id"], {
                "estado": "suspendido",
                "suspension": {"motivo": "deuda", "desde": ahora, "estado_anterior": antes},
            }, estado=antes)
            if hecho:
                await self.auditoria.registrar(
                    SISTEMA, "actualizar", "parqueadero", parqueadero["_id"], parqueadero["_id"],
                    antes={"estado": antes}, despues={"estado": "suspendido", "motivo": "deuda"},
                )

    async def _reactivar(self, socio: Document) -> None:
        """Solo los que suspendió la deuda; una suspensión por otro motivo no se toca."""
        for parqueadero in await self.parqueaderos.find(
            {"socio_id": socio["_id"], "estado": "suspendido", "suspension.motivo": "deuda"}, limit=0
        ):
            anterior = parqueadero["suspension"]["estado_anterior"]
            hecho = await self.parqueaderos.update(
                parqueadero["_id"], {"estado": anterior}, unset=["suspension"], estado="suspendido"
            )
            if hecho:
                await self.auditoria.registrar(
                    SISTEMA, "actualizar", "parqueadero", parqueadero["_id"], parqueadero["_id"],
                    antes={"estado": "suspendido", "motivo": "deuda"}, despues={"estado": anterior},
                )


def _liquida_desde(socio: Document) -> datetime:
    return as_utc(socio.get("liquida_desde") or socio["fecha_registro"])


def _saldo_pendiente(liquidacion: Optional[Document]) -> Decimal:
    if not liquidacion or liquidacion["estado"] != "pendiente":
        return CERO
    return to_decimal(liquidacion["total"])


def _uso_pct(deuda: Decimal, limite: Decimal) -> int:
    if deuda <= 0:
        return 0
    if limite <= 0:
        return 100
    return int(deuda * 100 / limite)


def _decimal(valor) -> Decimal:
    return to_decimal(valor) if isinstance(valor, (Decimal128, Decimal, int, str)) else CERO
