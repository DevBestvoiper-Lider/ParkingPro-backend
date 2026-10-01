import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from app.core.utils import (
    as_utc, fecha_local, formato_pesos, hoy_local, inicio_dia_utc, parse_oid, to_decimal, utcnow, ZONA,
)
from app.repositories.actividad_repository import ActividadRepository
from app.repositories.base import Document
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.reserva_repository import ESTADOS_ACTIVOS, ReservaRepository
from app.repositories.suscripcion_repository import SuscripcionRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.reserva import ReservaRead
from app.services.reserva_service import ReservaService

CERO = Decimal("0.00")
UMBRAL_CAPACIDAD_PCT = 90
DIAS_PENDIENTES = 30  # ventana para buscar reservas con saldo por cobrar


class AdminService:
    """Consultas del panel web. Los cálculos se hacen en Python: a la escala de un parqueadero
    (miles de reservas al mes) es simple y rápido; con más volumen convendría pasar a aggregate."""

    def __init__(
        self,
        reservas: ReservaRepository,
        espacios: EspacioRepository,
        usuarios: UsuarioRepository,
        suscripciones: SuscripcionRepository,
        actividad: ActividadRepository,
        reserva_service: ReservaService,
    ):
        self.reservas = reservas
        self.espacios = espacios
        self.usuarios = usuarios
        self.suscripciones = suscripciones
        self.actividad = actividad
        self.reserva_service = reserva_service

    # ---------- Dashboard ----------

    async def dashboard(self, empleado: Document, sede_id: Optional[str]) -> Document:
        filtro = _filtro_base(empleado, sede_id)
        ahora = utcnow()
        hoy = hoy_local()

        espacios = await self.espacios.find(filtro, limit=0)
        reservados = await self.reservas.espacios_reservados([e["_id"] for e in espacios], ahora, ahora + timedelta(hours=1))
        por_zona: Dict[str, Counter] = defaultdict(Counter)
        for espacio in espacios:
            por_zona[espacio.get("zona") or "Sin zona"][_estado_actual(espacio, reservados)] += 1
        total = len(espacios)
        plazas = _conteo(sum(por_zona.values(), Counter()))
        zonas = []
        for zona, conteo in sorted(por_zona.items()):
            fila = _conteo(conteo)
            zonas.append({
                "zona": zona,
                **fila,
                "porcentaje_del_total": round(fila["total"] / total * 100, 1),
                "porcentaje_ocupacion": round((fila["ocupadas"] + fila["reservadas"]) / fila["total"] * 100, 1),
            })

        dias = [hoy - timedelta(days=d) for d in range(6, -1, -1)]
        por_dia = await self._ingresos_por_dia(filtro, dias[0], hoy)
        ingresos_hoy, ingresos_ayer = por_dia.get(hoy, CERO), por_dia.get(hoy - timedelta(days=1), CERO)

        proximas = await self.reservas.find(
            {**filtro, "estado": {"$in": ESTADOS_ACTIVOS}, "fecha_inicio": {"$gte": ahora}, "sesion": {"$exists": False}},
            limit=5, sort=[("fecha_inicio", 1)],
        )
        pendientes_n, pendientes_monto = await self._pendientes_de_pago(filtro)

        parqueadero = await self.reserva_service.parqueaderos.get(empleado["parqueadero_id"])
        sedes = {s["_id"]: s["nombre"] for s in (parqueadero or {}).get("sedes", [])}
        alertas = [
            {"tipo": "mantenimiento",
             "titulo": " · ".join(filter(None, [f"Plaza {e['codigo']}", e.get("zona"), None if sede_id else sedes.get(e["sede_id"])])),
             "detalle": "En mantenimiento"}
            for e in espacios if e["estado"] == "mantenimiento"
        ]
        alertas += [
            {"tipo": "capacidad", "titulo": f"Capacidad alta en {z['zona']}",
             "detalle": f"{z['porcentaje_ocupacion']:.0f}% de ocupación actual"}
            for z in zonas if z["porcentaje_ocupacion"] >= UMBRAL_CAPACIDAD_PCT
        ]
        if pendientes_n:
            alertas.append({"tipo": "pendientes_pago", "titulo": f"{pendientes_n} reservas pendientes de pago",
                            "detalle": f"Monto total: {formato_pesos(pendientes_monto)}"})

        return {
            "plazas": plazas,
            "ingresos_hoy": ingresos_hoy,
            "ingresos_ayer": ingresos_ayer,
            "variacion_ingresos_pct": _variacion(ingresos_hoy, ingresos_ayer),
            "ocupacion_por_zona": zonas,
            "ingresos_ultimos_7_dias": [{"fecha": d, "total": por_dia.get(d, CERO)} for d in dias],
            "proximas_reservas": await self.reserva_service.enriquecer(proximas),
            "actividad_reciente": await self.listar_actividad(empleado, sede_id, 10),
            "alertas": alertas,
        }

    async def listar_actividad(self, empleado: Document, sede_id: Optional[str], limit: int) -> List[Document]:
        return await self.actividad.find(_filtro_base(empleado, sede_id), limit=limit, sort=[("fecha", -1)])

    # ---------- Reservas ----------

    async def estadisticas_reservas(self, empleado: Document, dia: Optional[date], sede_id: Optional[str]) -> Document:
        dia = dia or hoy_local()
        filtro = _filtro_base(empleado, sede_id)
        del_dia = await self.reservas.find({**filtro, "fecha_inicio": _rango_dias(dia, dia)}, limit=0)
        ayer = await self.reservas.count({**filtro, "fecha_inicio": _rango_dias(dia - timedelta(days=1), dia - timedelta(days=1))})
        estados = Counter(r["estado"] for r in del_dia)
        saldos = [s for s in (ReservaRead.model_validate(r).saldo for r in del_dia if r["estado"] != "cancelada") if s > 0]
        return {
            "fecha": dia,
            "total": len(del_dia),
            "variacion_vs_ayer": len(del_dia) - ayer,
            "confirmadas": estados["confirmada"],
            "pendientes": estados["pendiente"],
            "completadas": estados["completada"],
            "canceladas": estados["cancelada"],
            "pendientes_de_pago": len(saldos),
            "monto_pendiente": sum(saldos, CERO),
        }

    # ---------- Pagos ----------

    async def listar_pagos(
        self,
        empleado: Document,
        desde: Optional[date],
        hasta: Optional[date],
        metodo: Optional[str],
        estado: Optional[str],
        sede_id: Optional[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Document]:
        hasta = hasta or hoy_local()
        desde = desde or hasta
        movimientos = [
            (r, p) for r, p in await self._movimientos(_filtro_base(empleado, sede_id), desde, hasta)
            if (not metodo or p["metodo_pago"] == metodo) and (not estado or p["estado"] == estado)
        ]
        movimientos.sort(key=lambda m: m[1]["fecha_pago"], reverse=True)
        pagina = movimientos[skip:skip + limit] if limit else movimientos[skip:]
        await self.reserva_service.enriquecer(list({id(r): r for r, _ in pagina}.values()))
        return [
            {
                **p,
                "reserva_id": r["_id"],
                "reserva_codigo": r.get("codigo"),
                "cliente_nombre": r.get("cliente_nombre"),
                "placa": r.get("placa"),
            }
            for r, p in pagina
        ]

    async def resumen_pagos(self, empleado: Document, dia: Optional[date], sede_id: Optional[str]) -> Document:
        dia = dia or hoy_local()
        filtro = _filtro_base(empleado, sede_id)
        movimientos = await self._movimientos(filtro, dia - timedelta(days=1), dia)
        de_hoy = [p for _, p in movimientos if fecha_local(p["fecha_pago"]) == dia]
        pagos = [p for p in de_hoy if p["estado"] == "pagado"]
        reembolsos = [p for p in de_hoy if p["estado"] == "reembolsado"]
        por_dia = _sumar_por_dia(p for _, p in movimientos)
        recaudado, ayer = por_dia.get(dia, CERO), por_dia.get(dia - timedelta(days=1), CERO)
        pendientes_n, pendientes_monto = await self._pendientes_de_pago(filtro)
        bruto = sum((to_decimal(p["monto"]) for p in pagos), CERO)
        return {
            "fecha": dia,
            "recaudado": recaudado,
            "recaudado_ayer": ayer,
            "variacion_pct": _variacion(recaudado, ayer),
            "pendientes_monto": pendientes_monto,
            "pendientes_reservas": pendientes_n,
            "transacciones": len(de_hoy),
            "reembolsos_cantidad": len(reembolsos),
            "reembolsos_monto": sum((to_decimal(p["monto"]) for p in reembolsos), CERO),
            "metodos": _por_metodo(pagos),
            "ticket_promedio": (bruto / len(pagos)).quantize(Decimal("0.01")) if pagos else CERO,
        }

    # ---------- Clientes y vehículos ----------

    async def clientes(self, empleado: Document, q: Optional[str], skip: int, limit: int) -> List[Document]:
        reservas = await self.reservas.find({"parqueadero_id": empleado["parqueadero_id"]}, limit=0)
        stats: Dict = defaultdict(lambda: {"reservas": 0, "total_pagado": CERO, "ultima_visita": None})
        for r in reservas:
            s = stats[r["usuario_id"]]
            s["reservas"] += 1
            s["total_pagado"] += ReservaRead.model_validate(r).total_pagado
            if r["estado"] != "cancelada":
                s["ultima_visita"] = max(filter(None, [s["ultima_visita"], as_utc(r["fecha_inicio"])]))
        usuarios = await self.usuarios.find({"_id": {"$in": list(stats)}}, limit=0)
        afiliados = await self._afiliados([u["_id"] for u in usuarios])
        texto = (q or "").strip().lower()
        placa = texto.replace(" ", "").replace("-", "").upper()
        clientes = [
            {**u, **stats[u["_id"]], "afiliado": u["_id"] in afiliados}
            for u in usuarios
            if not texto
            or texto in u["nombre"].lower()
            or texto in u["email"]
            or any(placa in v["placa"] for v in u.get("vehiculos", []))
        ]
        clientes.sort(key=lambda c: c["ultima_visita"] or datetime.min.replace(tzinfo=ZONA), reverse=True)
        return clientes[skip:skip + limit]

    async def vehiculos(self, empleado: Document, q: Optional[str], skip: int, limit: int) -> List[Document]:
        reservas = await self.reservas.find({"parqueadero_id": empleado["parqueadero_id"]}, limit=0)
        visitas = Counter(r["vehiculo_id"] for r in reservas if r["estado"] != "cancelada")
        ultima: Dict = {}
        adentro = set()
        for r in reservas:
            if r["estado"] != "cancelada":
                ultima[r["vehiculo_id"]] = max(filter(None, [ultima.get(r["vehiculo_id"]), as_utc(r["fecha_inicio"])]))
            if (r.get("sesion") or {}).get("estado") == "activa":
                adentro.add(r["vehiculo_id"])
        usuarios = await self.usuarios.find({"_id": {"$in": list({r["usuario_id"] for r in reservas})}}, limit=0)
        placa = (q or "").replace(" ", "").replace("-", "").upper()
        vehiculos = [
            {**v, "cliente_id": u["_id"], "cliente_nombre": u["nombre"], "visitas": visitas[v["_id"]],
             "ultima_visita": ultima.get(v["_id"]), "adentro": v["_id"] in adentro}
            for u in usuarios for v in u.get("vehiculos", [])
            if v["_id"] in visitas or v["_id"] in adentro
            if not placa or placa in v["placa"]
        ]
        vehiculos.sort(key=lambda v: (not v["adentro"], -v["visitas"]))
        return vehiculos[skip:skip + limit]

    # ---------- Reportes ----------

    async def reporte(self, empleado: Document, desde: Optional[date], hasta: Optional[date], sede_id: Optional[str]) -> Document:
        hasta = hasta or hoy_local()
        desde = desde or hasta - timedelta(days=29)
        filtro = _filtro_base(empleado, sede_id)
        movimientos = await self._movimientos(filtro, desde, hasta)
        por_dia = _sumar_por_dia(p for _, p in movimientos)
        reservas = await self.reservas.find({**filtro, "fecha_inicio": _rango_dias(desde, hasta)}, limit=0)
        estados = Counter(r["estado"] for r in reservas)

        horas = Counter()
        duraciones = []
        for r in reservas:
            sesion = r.get("sesion") or {}
            if sesion.get("hora_entrada"):
                horas[as_utc(sesion["hora_entrada"]).astimezone(ZONA).hour] += 1
            if sesion.get("hora_entrada") and sesion.get("hora_salida"):
                duraciones.append((as_utc(sesion["hora_salida"]) - as_utc(sesion["hora_entrada"])).total_seconds() / 60)

        espacios = {e["_id"]: e for e in await self.espacios.find(filtro, limit=0)}
        por_zona: Dict[str, Decimal] = defaultdict(lambda: CERO)
        for r, p in movimientos:
            zona = (espacios.get(r["espacio_id"]) or {}).get("zona") or "Sin zona"
            por_zona[zona] += _con_signo(p)

        dias = [desde + timedelta(days=d) for d in range((hasta - desde).days + 1)]
        return {
            "desde": desde,
            "hasta": hasta,
            "ingresos_total": sum(por_dia.values(), CERO),
            "ingresos_por_dia": [{"fecha": d, "total": por_dia.get(d, CERO)} for d in dias],
            "ingresos_por_metodo": _por_metodo([p for _, p in movimientos if p["estado"] == "pagado"]),
            "reservas_por_estado": dict(estados),
            "tasa_cancelacion_pct": round(estados["cancelada"] / len(reservas) * 100, 1) if reservas else 0.0,
            "horas_pico": [{"hora": h, "entradas": n} for h, n in sorted(horas.items())],
            "duracion_promedio_min": round(sum(duraciones) / len(duraciones), 1) if duraciones else None,
            "ingreso_por_zona": {z: float(v) for z, v in sorted(por_zona.items())},
        }

    # ---------- Exportar ----------

    async def exportar_reservas(self, empleado: Document, **filtros) -> str:
        reservas = await self.reserva_service.listar_de_parqueadero(empleado, limit=0, **filtros)
        filas = []
        for r in reservas:
            leida = ReservaRead.model_validate(r)
            filas.append([
                leida.codigo, leida.cliente_nombre, leida.placa, leida.sede_nombre, leida.zona, leida.espacio_codigo,
                _hora(leida.fecha_inicio), _hora(leida.fecha_fin), leida.estado, leida.total, leida.total_pagado, leida.saldo,
            ])
        return _csv(["codigo", "cliente", "placa", "sede", "zona", "plaza", "entrada", "salida",
                     "estado", "total", "pagado", "saldo"], filas)

    async def exportar_pagos(self, empleado: Document, **filtros) -> str:
        pagos = await self.listar_pagos(empleado, limit=0, **filtros)
        return _csv(
            ["transaccion", "reserva", "cliente", "placa", "metodo", "monto", "estado", "fecha"],
            [[p.get("codigo"), p["reserva_codigo"], p["cliente_nombre"], p["placa"], p["metodo_pago"],
              to_decimal(p["monto"]), p["estado"], _hora(p["fecha_pago"])] for p in pagos],
        )

    # ---------- Helpers ----------

    async def _movimientos(self, filtro: Document, desde: date, hasta: date) -> List[Tuple[Document, Document]]:
        """(reserva, pago) de los pagos y reembolsos hechos entre `desde` y `hasta` (días locales, inclusive)."""
        rango = _rango_dias(desde, hasta)
        reservas = await self.reservas.find({**filtro, "pagos.fecha_pago": rango}, limit=0)
        inicio, fin = rango["$gte"], rango["$lt"]
        return [
            (r, p) for r in reservas for p in r.get("pagos", [])
            if inicio <= as_utc(p["fecha_pago"]) < fin and p["estado"] in ("pagado", "reembolsado")
        ]

    async def _ingresos_por_dia(self, filtro: Document, desde: date, hasta: date) -> Dict[date, Decimal]:
        return _sumar_por_dia(p for _, p in await self._movimientos(filtro, desde, hasta))

    async def _pendientes_de_pago(self, filtro: Document) -> Tuple[int, Decimal]:
        reservas = await self.reservas.find({
            **filtro,
            "estado": {"$in": ["pendiente", "confirmada", "completada"]},
            "fecha_inicio": {"$gte": utcnow() - timedelta(days=DIAS_PENDIENTES)},
        }, limit=0)
        saldos = [s for s in (ReservaRead.model_validate(r).saldo for r in reservas) if s > 0]
        return len(saldos), sum(saldos, CERO)

    async def _afiliados(self, usuario_ids: List) -> set:
        vigentes = await self.suscripciones.find({
            "usuario_id": {"$in": usuario_ids},
            "estado": {"$in": ["activa", "cancelada"]},
            "fecha_fin": {"$gt": utcnow()},
        }, limit=0)
        return {s["usuario_id"] for s in vigentes}


def _filtro_base(empleado: Document, sede_id: Optional[str]) -> Document:
    filtro: Document = {"parqueadero_id": empleado["parqueadero_id"]}
    if sede_id:
        filtro["sede_id"] = parse_oid(sede_id)
    return filtro


def _rango_dias(desde: date, hasta: date) -> Document:
    return {"$gte": inicio_dia_utc(desde), "$lt": inicio_dia_utc(hasta + timedelta(days=1))}


def _estado_actual(espacio: Document, reservados: set) -> str:
    if espacio["estado"] == "mantenimiento":
        return "mantenimiento"
    if espacio["estado"] == "ocupado":
        return "ocupadas"
    if espacio["_id"] in reservados:
        return "reservadas"
    return "disponibles"


def _conteo(c: Counter) -> Document:
    return {
        "total": sum(c.values()),
        "disponibles": c["disponibles"],
        "ocupadas": c["ocupadas"],
        "reservadas": c["reservadas"],
        "mantenimiento": c["mantenimiento"],
    }


def _con_signo(pago: Document) -> Decimal:
    monto = to_decimal(pago["monto"])
    return -monto if pago["estado"] == "reembolsado" else monto


def _sumar_por_dia(pagos: Iterable[Document]) -> Dict[date, Decimal]:
    por_dia: Dict[date, Decimal] = defaultdict(lambda: CERO)
    for p in pagos:
        por_dia[fecha_local(p["fecha_pago"])] += _con_signo(p)
    return dict(por_dia)


def _por_metodo(pagos: List[Document]) -> List[Document]:
    montos: Dict[str, Decimal] = defaultdict(lambda: CERO)
    for p in pagos:
        montos[p["metodo_pago"]] += to_decimal(p["monto"])
    total = sum(montos.values(), CERO)
    return sorted(
        ({"metodo_pago": m, "monto": v, "porcentaje": round(float(v / total * 100), 1) if total else 0.0}
         for m, v in montos.items()),
        key=lambda x: x["monto"], reverse=True,
    )


def _variacion(actual: Decimal, anterior: Decimal) -> Optional[float]:
    if not anterior:
        return None
    return round(float((actual - anterior) / anterior * 100), 1)


def _hora(dt: Optional[datetime]) -> str:
    return as_utc(dt).astimezone(ZONA).strftime("%Y-%m-%d %H:%M") if dt else ""


def _csv(encabezados: List[str], filas: List[list]) -> str:
    salida = io.StringIO()
    writer = csv.writer(salida)
    writer.writerow(encabezados)
    writer.writerows(["" if v is None else v for v in fila] for fila in filas)
    return salida.getvalue()
