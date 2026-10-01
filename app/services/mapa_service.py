from collections import Counter
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from bson import ObjectId

from app.core.utils import haversine_km, utcnow
from app.models.enums import TARIFA_POR_TIPO_ESPACIO
from app.repositories.base import Document
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.interes_repository import InteresRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.reserva_repository import ReservaRepository
from app.repositories.tarifa_repository import TarifaRepository

# Un espacio cuenta como libre si no tiene reservas en la próxima hora.
VENTANA_LIBRE = timedelta(hours=1)


class MapaService:
    def __init__(
        self,
        parqueaderos: ParqueaderoRepository,
        espacios: EspacioRepository,
        tarifas: TarifaRepository,
        reservas: ReservaRepository,
        interesados: InteresRepository,
    ):
        self.parqueaderos = parqueaderos
        self.espacios = espacios
        self.tarifas = tarifas
        self.reservas = reservas
        self.interesados = interesados

    async def cercanos(
        self, latitud: float, longitud: float, radio_km: float, tipo: Optional[str], texto: Optional[str]
    ) -> List[Document]:
        """Sedes activas dentro del radio, de la más cercana a la más lejana."""
        # Distancia calculada en Python: suficiente a escala de ciudad. Con miles de sedes,
        # conviene un índice 2dsphere y $geoNear.
        parqueaderos = await self.parqueaderos.find(
            {"estado": {"$ne": "suspendido"}, "sedes.ubicacion": {"$exists": True}}, limit=0
        )
        texto = (texto or "").strip().lower()
        cercanas = []
        for parqueadero in parqueaderos:
            for sede in parqueadero.get("sedes", []):
                if sede["estado"] != "activa" or not sede.get("ubicacion"):
                    continue
                sede_lng, sede_lat = sede["ubicacion"]["coordinates"]
                distancia = haversine_km(latitud, longitud, sede_lat, sede_lng)
                if distancia > radio_km:
                    continue
                if texto and texto not in f"{parqueadero['nombre']} {sede['nombre']} {sede['direccion']}".lower():
                    continue
                cercanas.append((distancia, parqueadero, sede))
        cercanas.sort(key=lambda c: c[0])

        sede_ids = [sede["_id"] for _, _, sede in cercanas]
        libres, totales = await self._espacios_libres(sede_ids, tipo)
        precios = await self._precio_desde(sede_ids, tipo)
        interes = await self.interesados.por_sede(sede_ids)
        return [
            {
                "parqueadero_id": parqueadero["_id"],
                "parqueadero_nombre": parqueadero["nombre"],
                "sede_id": sede["_id"],
                "nombre": sede["nombre"],
                "direccion": sede["direccion"],
                "ciudad": sede["ciudad"],
                "telefono": sede.get("telefono"),
                "latitud": sede["ubicacion"]["coordinates"][1],
                "longitud": sede["ubicacion"]["coordinates"][0],
                "distancia_km": round(distancia, 2),
                "precio_hora_desde": precios.get(sede["_id"]),
                "espacios_libres": libres.get(sede["_id"], 0),
                "espacios_total": totales.get(sede["_id"], 0),
                "interesados": interes.get(sede["_id"], 0),
            }
            for distancia, parqueadero, sede in cercanas
        ]

    async def _espacios_libres(self, sede_ids: List[ObjectId], tipo: Optional[str]) -> Tuple[Counter, Counter]:
        """(libres ahora, total operativo) por sede. Operativo = no está en mantenimiento."""
        filtro: Document = {"sede_id": {"$in": sede_ids}, "estado": {"$ne": "mantenimiento"}}
        if tipo:
            filtro["tipo"] = tipo
        espacios = await self.espacios.find(filtro, limit=0)
        disponibles = [e for e in espacios if e["estado"] == "disponible"]
        ahora = utcnow()
        reservados = await self.reservas.espacios_reservados([e["_id"] for e in disponibles], ahora, ahora + VENTANA_LIBRE)
        libres = Counter(e["sede_id"] for e in disponibles if e["_id"] not in reservados)
        return libres, Counter(e["sede_id"] for e in espacios)

    async def _precio_desde(self, sede_ids: List[ObjectId], tipo: Optional[str]) -> Dict[ObjectId, Decimal]:
        filtro: Document = {"sede_id": {"$in": sede_ids}}
        if tipo:
            filtro["tipo_vehiculo"] = TARIFA_POR_TIPO_ESPACIO[tipo]
        precios: Dict[ObjectId, Decimal] = {}
        for tarifa in await self.tarifas.find(filtro, limit=0):
            valor = tarifa["valor_hora"].to_decimal()
            precios[tarifa["sede_id"]] = min(precios.get(tarifa["sede_id"], valor), valor)
        return precios
