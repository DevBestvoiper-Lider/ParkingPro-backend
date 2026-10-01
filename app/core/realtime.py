"""Canal de tiempo real por sede (WebSocket).

Sin Redis, los eventos solo llegan a los clientes conectados al mismo proceso. Con `REDIS_URL`,
cada proceso publica en Redis y todos reenvían a sus clientes: así funciona con varios workers
o varias instancias detrás de un balanceador.
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

CANAL = "parkingpro:sede:"


class HubTiempoReal:
    def __init__(self) -> None:
        self._conexiones: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self._redis = None
        self._escucha: Optional[asyncio.Task] = None

    async def iniciar(self, redis_url: Optional[str] = None, cliente=None) -> None:
        """Activa Redis pub/sub si hay URL (o un cliente ya creado, útil en tests)."""
        if not (redis_url or cliente):
            return
        if cliente is None:
            from redis import asyncio as aioredis
            cliente = aioredis.from_url(redis_url, decode_responses=True)
        self._redis = cliente
        pubsub = cliente.pubsub()
        await pubsub.psubscribe(f"{CANAL}*")
        self._escucha = asyncio.create_task(self._escuchar(pubsub))
        logger.info("Tiempo real usando Redis pub/sub")

    async def detener(self) -> None:
        if self._escucha:
            self._escucha.cancel()
            self._escucha = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def conectar(self, sede_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._conexiones[sede_id].add(websocket)

    def desconectar(self, sede_id: str, websocket: WebSocket) -> None:
        self._conexiones[sede_id].discard(websocket)
        if not self._conexiones[sede_id]:
            del self._conexiones[sede_id]

    async def publicar(self, sede_id: str, mensaje: Dict[str, Any]) -> None:
        if self._redis is not None:
            try:
                await self._redis.publish(CANAL + sede_id, json.dumps(mensaje))
                return
            except Exception:
                logger.exception("No se pudo publicar en Redis; se envía solo a este proceso")
        await self._enviar_local(sede_id, mensaje)

    async def _escuchar(self, pubsub) -> None:
        while True:
            try:
                async for mensaje in pubsub.listen():
                    if mensaje["type"] == "pmessage":
                        sede_id = mensaje["channel"][len(CANAL):]
                        await self._enviar_local(sede_id, json.loads(mensaje["data"]))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error escuchando Redis; reintentando en 5 s")
                await asyncio.sleep(5)

    async def _enviar_local(self, sede_id: str, mensaje: Dict[str, Any]) -> None:
        for websocket in list(self._conexiones.get(sede_id, ())):
            try:
                await websocket.send_json(mensaje)
            except Exception:  # conexión caída: la quitamos
                self.desconectar(sede_id, websocket)


hub = HubTiempoReal()
