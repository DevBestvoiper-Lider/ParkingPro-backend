import math
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.utils import (
    as_utc, clean, formato_fecha_hora, formato_pesos, parse_oid, to_decimal, to_decimal128, utcnow,
)
from app.models.enums import TARIFA_POR_TIPO_ESPACIO
from app.repositories.base import Document
from app.repositories.contador_repository import ContadorRepository
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.reserva_repository import ESTADOS_ACTIVOS, ReservaRepository
from app.repositories.suscripcion_repository import SuscripcionRepository
from app.repositories.tarifa_repository import TarifaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import Principal
from app.schemas.reserva import (
    CheckInManual, CheckOutManual, PagoCreate, ReembolsoCreate, ReservaCreate, ReservaRead,
)
from app.services.actividad_usuario import calcular_actividad
from app.services.eventos import Eventos
from app.services.notificacion_service import NotificacionService


class ReservaService:
    def __init__(
        self,
        repository: ReservaRepository,
        espacios: EspacioRepository,
        tarifas: TarifaRepository,
        parqueaderos: ParqueaderoRepository,
        usuarios: UsuarioRepository,
        contadores: ContadorRepository,
        suscripciones: SuscripcionRepository,
        eventos: Eventos,
        notificaciones: NotificacionService,
    ):
        self.repository = repository
        self.espacios = espacios
        self.tarifas = tarifas
        self.parqueaderos = parqueaderos
        self.usuarios = usuarios
        self.contadores = contadores
        self.suscripciones = suscripciones
        self.eventos = eventos
        self.notificaciones = notificaciones

    # ---------- Consultas ----------

    async def listar_de_usuario(
        self, usuario: Document, estados: Optional[List[str]], skip: int, limit: int
    ) -> List[Document]:
        filtro: Document = {"usuario_id": usuario["_id"]}
        if estados:
            filtro["estado"] = {"$in": estados}
        reservas = await self.repository.find(filtro, skip, limit, sort=[("fecha_inicio", -1)])
        return await self.enriquecer(reservas)

    async def listar_de_parqueadero(
        self,
        empleado: Document,
        sede_id: Optional[str] = None,
        estados: Optional[List[str]] = None,
        codigo: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
        q: Optional[str] = None,
        zona: Optional[str] = None,
    ) -> List[Document]:
        filtro = await self.filtro_parqueadero(empleado, sede_id, estados, codigo, desde, hasta, q, zona)
        if filtro is None:
            return []
        reservas = await self.repository.find(filtro, skip, limit, sort=[("fecha_inicio", -1)])
        return await self.enriquecer(reservas)

    async def filtro_parqueadero(
        self,
        empleado: Document,
        sede_id: Optional[str],
        estados: Optional[List[str]],
        codigo: Optional[str],
        desde: Optional[datetime],
        hasta: Optional[datetime],
        q: Optional[str] = None,
        zona: Optional[str] = None,
    ) -> Optional[Document]:
        """Filtro de Mongo para el listado del panel. None si la búsqueda no puede dar resultados."""
        filtro: Document = {"parqueadero_id": empleado["parqueadero_id"]}
        if sede_id:
            filtro["sede_id"] = parse_oid(sede_id)
        if estados:
            filtro["estado"] = {"$in": estados}
        if codigo:
            filtro["codigo"] = codigo
        rango = clean({"$gte": desde and as_utc(desde), "$lt": hasta and as_utc(hasta)})
        if rango:
            filtro["fecha_inicio"] = rango
        if zona:
            espacios = await self.espacios.find({"parqueadero_id": empleado["parqueadero_id"], "zona": zona}, limit=0)
            filtro["espacio_id"] = {"$in": [e["_id"] for e in espacios]}
        if q:
            # Busca por código de reserva, placa o nombre del cliente.
            texto = q.strip()
            placa = texto.replace(" ", "").replace("-", "").upper()
            usuarios = await self.usuarios.find({"$or": [
                {"nombre": {"$regex": re.escape(texto), "$options": "i"}},
                {"vehiculos.placa": {"$regex": re.escape(placa)}},
            ]}, limit=200)
            vehiculos = [v["_id"] for u in usuarios for v in u.get("vehiculos", []) if placa in v["placa"]]
            por_nombre = [u["_id"] for u in usuarios if texto.lower() in u["nombre"].lower()]
            opciones: List[Document] = [{"codigo": {"$regex": re.escape(texto), "$options": "i"}}]
            if vehiculos:
                opciones.append({"vehiculo_id": {"$in": vehiculos}})
            if por_nombre:
                opciones.append({"usuario_id": {"$in": por_nombre}})
            filtro["$or"] = opciones
        return filtro

    async def obtener(self, principal: Principal, reserva_id: str) -> Document:
        return await self._enriquecer_uno(await self._obtener(principal, reserva_id))

    async def resumen(self, usuario: Document) -> Document:
        """Contadores y sesión activa para la pantalla de Inicio."""
        proximas = await self.repository.count({
            "usuario_id": usuario["_id"],
            "estado": {"$in": ESTADOS_ACTIVOS},
            "fecha_fin": {"$gt": utcnow()},
            "sesion": {"$exists": False},
        })
        activa = await self.repository.collection.find_one({"usuario_id": usuario["_id"], "sesion.estado": "activa"})
        suscripcion = await self.suscripciones.vigente(usuario["_id"])
        return {
            "reservas_proximas": proximas,
            "vehiculos": len(usuario.get("vehiculos", [])),
            "sesion_activa": activa and await self._enriquecer_uno(activa),
            "plan": "afiliado" if suscripcion else "por_uso",
            "notificaciones_no_leidas": await self.notificaciones.no_leidas(usuario),
        }

    async def actividad(self, usuario: Document) -> Document:
        """Consumo del usuario para la pantalla Mi actividad."""
        reservas = await self.repository.find({"usuario_id": usuario["_id"]}, limit=0)
        return calcular_actividad(await self.enriquecer(reservas))

    # ---------- Ciclo de vida ----------

    async def crear(self, usuario: Document, data: ReservaCreate) -> Document:
        vehiculo_id = parse_oid(data.vehiculo_id)
        if not any(v["_id"] == vehiculo_id for v in usuario.get("vehiculos", [])):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El vehículo no pertenece al usuario")

        inicio, fin = as_utc(data.fecha_inicio), as_utc(data.fecha_fin)
        ahora = utcnow()
        if fin <= ahora:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La reserva debe terminar en el futuro")

        sede_id = parse_oid(data.sede_id)
        parqueadero, sede = await self._sede_abierta(sede_id)

        espacio = await self.espacios.get(parse_oid(data.espacio_id), sede_id=sede_id)
        if not espacio:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado en la sede")
        if espacio["estado"] == "mantenimiento":
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio está en mantenimiento")
        if espacio["estado"] == "ocupado" and inicio <= ahora:
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio está ocupado en este momento")

        tarifa = await self.tarifas.get(parse_oid(data.tarifa_id), sede_id=sede_id)
        if not tarifa:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarifa no encontrada en la sede")
        if tarifa["tipo_vehiculo"] != TARIFA_POR_TIPO_ESPACIO[espacio["tipo"]]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La tarifa no corresponde al tipo de espacio")

        if await self.repository.espacios_reservados([espacio["_id"]], inicio, fin):
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio ya está reservado en ese horario")

        suscripcion = await self.suscripciones.vigente(usuario["_id"])
        if not suscripcion:
            libres, total = await self._libres(sede_id, espacio["tipo"], inicio, fin)
            cupo_afiliados = math.floor(total * settings.AFILIADO_CUPO_PRIORITARIO_PCT / 100)
            if len(libres) <= cupo_afiliados:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Hora pico: los últimos cupos están reservados para el plan Afiliado",
                )

        reserva = await self.repository.insert(await self._nueva_reserva(
            parqueadero, sede_id, usuario, vehiculo_id, espacio, tarifa, suscripcion, inicio, fin, "pendiente"
        ))
        reserva = await self._enriquecer_uno(reserva)
        await self._evento(reserva, "reserva_creada",
                           f"{reserva['codigo']} · {reserva.get('placa', '')} para {formato_fecha_hora(inicio)}")
        return reserva

    async def check_in_manual(self, empleado: Document, data: CheckInManual) -> Document:
        """Entrada en caseta sin reserva: crea la reserva y la sesión en un solo paso."""
        sede_id = parse_oid(data.sede_id)
        parqueadero, sede = await self._sede_abierta(sede_id)
        if parqueadero["_id"] != empleado["parqueadero_id"]:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")

        usuario, vehiculo = await self._cliente_por_placa(data.placa, data.nombre_cliente)
        if await self.repository.exists({"vehiculo_id": vehiculo["_id"], "sesion.estado": "activa"}):
            raise HTTPException(status.HTTP_409_CONFLICT, f"El vehículo {data.placa} ya está adentro")

        inicio = utcnow()
        fin = inicio + timedelta(hours=data.horas_estimadas)
        if data.espacio_id:
            espacio = await self.espacios.get(parse_oid(data.espacio_id), sede_id=sede_id)
            if not espacio:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Espacio no encontrado en la sede")
            if await self.repository.espacios_reservados([espacio["_id"]], inicio, fin):
                raise HTTPException(status.HTTP_409_CONFLICT, "El espacio tiene una reserva en ese horario")
        else:
            libres, _ = await self._libres(sede_id, data.tipo_espacio, inicio, fin)
            if not libres:
                raise HTTPException(status.HTTP_409_CONFLICT, f"No hay espacios {data.tipo_espacio} libres")
            espacio = libres[0]

        tipo_tarifa = TARIFA_POR_TIPO_ESPACIO[espacio["tipo"]]
        if data.tarifa_id:
            tarifa = await self.tarifas.get(parse_oid(data.tarifa_id), sede_id=sede_id, tipo_vehiculo=tipo_tarifa)
        else:
            tarifas = await self.tarifas.find({"sede_id": sede_id, "tipo_vehiculo": tipo_tarifa}, limit=0)
            tarifa = min(tarifas, key=lambda t: to_decimal(t["valor_hora"]), default=None)
        if not tarifa:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay tarifa para ese tipo de espacio")

        if not await self.espacios.ocupar(espacio["_id"]):
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio no está disponible")
        suscripcion = await self.suscripciones.vigente(usuario["_id"])
        doc = await self._nueva_reserva(
            parqueadero, sede_id, usuario, vehiculo["_id"], espacio, tarifa, suscripcion, inicio, fin, "confirmada"
        )
        doc["sesion"] = {"hora_entrada": inicio, "estado": "activa"}
        reserva = await self._enriquecer_uno(await self.repository.insert(doc))
        await self._evento(reserva, "check_in", f"{reserva['placa']} en {_ubicacion(reserva)}", "ocupado")
        return reserva

    async def check_out_manual(self, empleado: Document, data: CheckOutManual) -> Document:
        usuarios = await self.usuarios.find({"vehiculos.placa": data.placa}, limit=0)
        vehiculos = [v["_id"] for u in usuarios for v in u["vehiculos"] if v["placa"] == data.placa]
        reserva = await self.repository.collection.find_one({
            "parqueadero_id": empleado["parqueadero_id"],
            "vehiculo_id": {"$in": vehiculos},
            "sesion.estado": "activa",
        })
        if not reserva:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No hay una sesión activa para {data.placa}")
        return await self.registrar_salida(Principal("empleado", empleado), str(reserva["_id"]))

    async def confirmar(self, empleado: Document, reserva_id: str) -> Document:
        reserva = await self._de_parqueadero(empleado, reserva_id)
        actualizada = await self.repository.update(reserva["_id"], {"estado": "confirmada"}, estado="pendiente")
        if not actualizada:
            raise HTTPException(status.HTTP_409_CONFLICT, "Solo se pueden confirmar reservas pendientes")
        return await self._al_confirmar(actualizada)

    async def cancelar(self, principal: Principal, reserva_id: str) -> Document:
        reserva = await self._obtener(principal, reserva_id)
        actualizada = await self.repository.update(
            reserva["_id"],
            {"estado": "cancelada"},
            estado={"$in": ESTADOS_ACTIVOS},
            sesion={"$exists": False},
        )
        if not actualizada:
            raise HTTPException(status.HTTP_409_CONFLICT, "La reserva no se puede cancelar en su estado actual")
        actualizada = await self._enriquecer_uno(actualizada)
        await self._evento(actualizada, "reserva_cancelada", f"{actualizada['codigo']} · {actualizada.get('placa', '')}")
        if principal.es_empleado:
            await self.notificaciones.notificar(
                actualizada["usuario_id"], "Reserva cancelada",
                f"El parqueadero canceló tu reserva {actualizada['codigo']}.", reserva_id=actualizada["_id"],
            )
        await self._cupo_liberado(actualizada)
        return actualizada

    async def registrar_entrada(self, empleado: Document, reserva_id: str) -> Document:
        reserva = await self._de_parqueadero(empleado, reserva_id)
        if reserva["estado"] not in ESTADOS_ACTIVOS or reserva.get("sesion"):
            raise HTTPException(status.HTTP_409_CONFLICT, "La reserva no admite registrar entrada")

        if not await self.espacios.ocupar(reserva["espacio_id"]):
            raise HTTPException(status.HTTP_409_CONFLICT, "El espacio no está disponible")

        actualizada = await self.repository.update(
            reserva["_id"],
            {"estado": "confirmada", "sesion": {"hora_entrada": utcnow(), "estado": "activa"}},
            estado={"$in": ESTADOS_ACTIVOS},
            sesion={"$exists": False},
        )
        if not actualizada:
            # Otra petición cambió la reserva entre medio: devolvemos el espacio.
            await self.espacios.liberar(reserva["espacio_id"])
            raise HTTPException(status.HTTP_409_CONFLICT, "La reserva cambió de estado, intenta de nuevo")
        actualizada = await self._enriquecer_uno(actualizada)
        await self._evento(actualizada, "check_in", f"{actualizada.get('placa', '')} en {_ubicacion(actualizada)}", "ocupado")
        return actualizada

    async def registrar_salida(self, principal: Principal, reserva_id: str) -> Document:
        """La registra un empleado, o el propio usuario con 'Finalizar sesión' en la app."""
        reserva = await self._obtener(principal, reserva_id)
        actualizada = await self.repository.update(
            reserva["_id"],
            {"estado": "completada", "sesion.hora_salida": utcnow(), "sesion.estado": "finalizada"},
            **{"sesion.estado": "activa"},
        )
        if not actualizada:
            raise HTTPException(status.HTTP_409_CONFLICT, "La reserva no tiene una sesión activa")
        await self.espacios.liberar(reserva["espacio_id"])
        actualizada = await self._enriquecer_uno(actualizada)
        total = ReservaRead.model_validate(actualizada).total
        await self._evento(actualizada, "check_out",
                           f"{actualizada.get('placa', '')} – Total: {formato_pesos(total)}", "disponible")
        await self._cupo_liberado(actualizada)
        return actualizada

    async def registrar_pago(self, principal: Principal, reserva_id: str, data: PagoCreate) -> Document:
        if principal.es_usuario and data.metodo_pago != "app":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Desde la app solo se puede pagar con metodo_pago 'app'")
        if principal.es_empleado and data.metodo_pago == "app":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "En caja usa 'efectivo' o 'tarjeta'")

        reserva = await self._obtener(principal, reserva_id)
        if reserva["estado"] == "cancelada":
            raise HTTPException(status.HTTP_409_CONFLICT, "La reserva está cancelada")

        saldo = ReservaRead.model_validate(reserva).saldo
        if data.monto > saldo:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"El monto supera el saldo pendiente ({saldo})")

        # TODO: con una pasarela real, los pagos 'app' deberían quedar 'pendiente' hasta su confirmación.
        pago = await self._nuevo_pago(data.monto, data.metodo_pago, "pagado")
        actualizada = await self.repository.add_pago(reserva["_id"], pago)
        await self._evento(await self._enriquecer_uno(actualizada), "pago",
                           f"{formato_pesos(data.monto)} – {reserva['codigo']} ({data.metodo_pago})")

        # Pre-pago: pagar completa una reserva pendiente la confirma y asegura el espacio.
        if actualizada["estado"] == "pendiente" and ReservaRead.model_validate(actualizada).saldo <= 0:
            confirmada = await self.repository.update(reserva["_id"], {"estado": "confirmada"}, estado="pendiente")
            if confirmada:
                return await self._al_confirmar(confirmada)
        return await self._enriquecer_uno(actualizada)

    async def reembolsar(self, empleado: Document, reserva_id: str, data: ReembolsoCreate) -> Document:
        reserva = await self._de_parqueadero(empleado, reserva_id)
        pagado = ReservaRead.model_validate(reserva).total_pagado
        if data.monto > pagado:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No se puede reembolsar más de lo pagado ({pagado})")
        pago = await self._nuevo_pago(data.monto, data.metodo_pago, "reembolsado")
        actualizada = await self._enriquecer_uno(await self.repository.add_pago(reserva["_id"], pago))
        await self._evento(actualizada, "reembolso", f"-{formato_pesos(data.monto)} – {reserva['codigo']}")
        await self.notificaciones.notificar(
            reserva["usuario_id"], "Reembolso realizado",
            f"Te reembolsamos {formato_pesos(data.monto)} de la reserva {reserva['codigo']}.", reserva_id=reserva["_id"],
        )
        return actualizada

    async def nuevo_codigo(self) -> str:
        return f"Rsv-{await self.contadores.siguiente('reservas'):06d}"

    # ---------- Helpers ----------

    async def _sede_abierta(self, sede_id: ObjectId) -> Tuple[Document, Document]:
        encontrado = await self.parqueaderos.get_sede(sede_id)
        if not encontrado:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sede no encontrada")
        parqueadero, sede = encontrado
        if parqueadero["estado"] == "suspendido" or sede["estado"] != "activa":
            raise HTTPException(status.HTTP_409_CONFLICT, "La sede no está recibiendo reservas")
        return parqueadero, sede

    async def _libres(self, sede_id: ObjectId, tipo: str, inicio: datetime, fin: datetime) -> Tuple[List[Document], int]:
        """(espacios libres de ese tipo en el horario, total de espacios operativos de ese tipo)."""
        espacios = await self.espacios.find(
            {"sede_id": sede_id, "tipo": tipo, "estado": {"$ne": "mantenimiento"}}, limit=0, sort=[("zona", 1), ("codigo", 1)]
        )
        reservados = await self.repository.espacios_reservados([e["_id"] for e in espacios], inicio, fin)
        empieza_ya = inicio <= utcnow()
        libres = [
            e for e in espacios
            if e["_id"] not in reservados and not (e["estado"] == "ocupado" and empieza_ya)
        ]
        return libres, len(espacios)

    async def _nueva_reserva(
        self,
        parqueadero: Document,
        sede_id: ObjectId,
        usuario: Document,
        vehiculo_id: ObjectId,
        espacio: Document,
        tarifa: Document,
        suscripcion: Optional[Document],
        inicio: datetime,
        fin: datetime,
        estado: str,
    ) -> Document:
        # Copia de la tarifa: si luego cambia el precio, la reserva conserva el suyo.
        tarifa_aplicada: Document = {"nombre": tarifa["nombre"], "valor_hora": tarifa["valor_hora"]}
        if suscripcion:
            descuento = suscripcion["descuento_pct"]
            valor = to_decimal(tarifa["valor_hora"]) * (Decimal(100 - descuento) / 100)
            tarifa_aplicada = {
                "nombre": f"{tarifa['nombre']} (Afiliado -{descuento}%)",
                "valor_hora": to_decimal128(valor),
                "descuento_pct": descuento,
            }
        return {
            "parqueadero_id": parqueadero["_id"],
            "sede_id": sede_id,
            "usuario_id": usuario["_id"],
            "vehiculo_id": vehiculo_id,
            "espacio_id": espacio["_id"],
            "tarifa_id": tarifa["_id"],
            "codigo": await self.nuevo_codigo(),
            "fecha_inicio": inicio,
            "fecha_fin": fin,
            "estado": estado,
            "tarifa_aplicada": tarifa_aplicada,
            "pagos": [],
        }

    async def _nuevo_pago(self, monto: Decimal, metodo: str, estado: str) -> Document:
        return {
            "_id": ObjectId(),
            "codigo": f"TX-{await self.contadores.siguiente('pagos'):06d}",
            "monto": to_decimal128(monto),
            "fecha_pago": utcnow(),
            "metodo_pago": metodo,
            "estado": estado,
        }

    async def _cliente_por_placa(self, placa: str, nombre: Optional[str]) -> Tuple[Document, Document]:
        """Dueño registrado del vehículo o, si no existe, un cliente ocasional (sin acceso a la app)."""
        usuario = await self.usuarios.collection.find_one({"vehiculos.placa": placa})
        if usuario:
            vehiculo = next(v for v in usuario["vehiculos"] if v["placa"] == placa)
            return usuario, vehiculo
        vehiculo = {"_id": ObjectId(), "placa": placa}
        usuario = await self.usuarios.insert({
            "nombre": nombre or "Cliente ocasional",
            "email": f"{placa.lower()}@ocasional.parkingpro",
            "vehiculos": [vehiculo],
        })
        return usuario, vehiculo

    async def _al_confirmar(self, reserva: Document) -> Document:
        reserva = await self._enriquecer_uno(reserva)
        await self._evento(reserva, "reserva_confirmada",
                           f"{reserva.get('placa', '')} para {formato_fecha_hora(reserva['fecha_inicio'])}")
        await self.notificaciones.notificar(
            reserva["usuario_id"], "¡Reserva confirmada!",
            f"{reserva['codigo']} · {_ubicacion(reserva)} · {formato_fecha_hora(reserva['fecha_inicio'])}",
            reserva_id=reserva["_id"], sede_id=reserva["sede_id"],
        )
        return reserva

    async def _cupo_liberado(self, reserva: Document) -> None:
        encontrado = await self.parqueaderos.get_sede(reserva["sede_id"])
        espacio = await self.espacios.get(reserva["espacio_id"])
        if encontrado and espacio:
            await self.notificaciones.cupo_liberado(encontrado[1], espacio)

    async def _evento(self, reserva: Document, tipo: str, descripcion: str, estado_espacio: Optional[str] = None) -> None:
        await self.eventos.registrar(
            reserva["parqueadero_id"], reserva["sede_id"], tipo, descripcion,
            reserva_id=reserva["_id"], espacio_id=reserva["espacio_id"], estado_espacio=estado_espacio,
        )

    @staticmethod
    def _tiene_acceso(principal: Principal, reserva: Document) -> bool:
        if principal.es_usuario:
            return reserva["usuario_id"] == principal.id
        return reserva["parqueadero_id"] == principal.doc["parqueadero_id"]

    async def _obtener(self, principal: Principal, reserva_id: str) -> Document:
        reserva = await self.repository.get(parse_oid(reserva_id))
        if not reserva or not self._tiene_acceso(principal, reserva):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Reserva no encontrada")
        return reserva

    async def _de_parqueadero(self, empleado: Document, reserva_id: str) -> Document:
        return await self._obtener(Principal("empleado", empleado), reserva_id)

    async def _enriquecer_uno(self, reserva: Document) -> Document:
        return (await self.enriquecer([reserva]))[0]

    async def enriquecer(self, reservas: List[Document]) -> List[Document]:
        """Agrega sede, plaza, placa y cliente para mostrarlos sin llamadas extra."""
        if not reservas:
            return reservas
        espacios = {
            e["_id"]: e
            for e in await self.espacios.find({"_id": {"$in": list({r["espacio_id"] for r in reservas})}}, limit=0)
        }
        parqueaderos = await self.parqueaderos.find(
            {"sedes._id": {"$in": list({r["sede_id"] for r in reservas})}}, limit=0
        )
        sedes = {s["_id"]: (p, s) for p in parqueaderos for s in p.get("sedes", [])}
        usuarios = {
            u["_id"]: u
            for u in await self.usuarios.find({"_id": {"$in": list({r["usuario_id"] for r in reservas})}}, limit=0)
        }
        for reserva in reservas:
            espacio = espacios.get(reserva["espacio_id"])
            parqueadero, sede = sedes.get(reserva["sede_id"], (None, None))
            usuario = usuarios.get(reserva["usuario_id"])
            vehiculo = next(
                (v for v in (usuario or {}).get("vehiculos", []) if v["_id"] == reserva["vehiculo_id"]), None
            )
            reserva.update(clean({
                "parqueadero_nombre": parqueadero and parqueadero["nombre"],
                "sede_nombre": sede and sede["nombre"],
                "espacio_codigo": espacio and espacio["codigo"],
                "zona": espacio and espacio.get("zona"),
                "placa": vehiculo and vehiculo["placa"],
                "cliente_nombre": usuario and usuario["nombre"],
            }))
        return reservas


def _ubicacion(reserva: Document) -> str:
    partes = [reserva.get("zona"), f"Plaza {reserva['espacio_codigo']}" if reserva.get("espacio_codigo") else None]
    return " - ".join(p for p in partes if p) or reserva.get("sede_nombre", "")

