import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from app.core.realtime import HubTiempoReal
from app.core.utils import utcnow
from app.tasks.jobs import vencer_reservas_pendientes, vencer_suscripciones
from tests.test_parkingpro import API, _reserva_body, _setup_parqueadero, _setup_usuario

pytestmark = pytest.mark.asyncio


async def _afiliar(client, headers):
    res = await client.post(f"{API}/suscripciones", headers=headers, json={"metodo_pago": "app"})
    assert res.status_code == 201, res.text
    return res.json()


async def test_planes_y_suscripcion(client):
    planes = (await client.get(f"{API}/suscripciones/planes")).json()
    assert [p["plan"] for p in planes] == ["por_uso", "afiliado"]
    assert planes[1]["precio_mensual"] == 29900 and planes[1]["descuento_pct"] == 15

    usuario, _ = await _setup_usuario(client)
    assert (await client.get(f"{API}/suscripciones/mia", headers=usuario)).json() is None
    s = await _afiliar(client, usuario)
    assert s["estado"] == "activa"
    assert (await client.post(f"{API}/suscripciones", headers=usuario, json={})).status_code == 409

    # Cancelar mantiene los beneficios hasta fecha_fin
    assert (await client.post(f"{API}/suscripciones/mia/cancelar", headers=usuario)).json()["estado"] == "cancelada"
    assert (await client.get(f"{API}/suscripciones/mia", headers=usuario)).json()["estado"] == "cancelada"
    assert (await client.get(f"{API}/reservas/mias/resumen", headers=usuario)).json()["plan"] == "afiliado"


async def test_afiliado_tiene_descuento(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    await _afiliar(client, usuario)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    r = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()
    assert r["tarifa_aplicada"] == {"nombre": "Carro diurna (Afiliado -15%)", "valor_hora": 3825, "descuento_pct": 15}
    assert r["total"] == 7650


async def test_hora_pico_reserva_ultimos_cupos_para_afiliados(client):
    p = await _setup_parqueadero(client)
    for i in range(9):  # 10 plazas de carro: el 10% (1) queda para afiliados
        await client.post(f"{API}/espacios", headers=p["admin"], json={"sede_id": p["sede_id"], "codigo": f"B-{i}", "tipo": "carro"})
    plazas = (await client.get(f"{API}/espacios", headers=p["admin"], params={"sede_id": p["sede_id"]})).json()
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)

    normal, vehiculo = await _setup_usuario(client)
    for plaza in plazas[:9]:
        body = {**_reserva_body(p, vehiculo, inicio), "espacio_id": plaza["id"]}
        assert (await client.post(f"{API}/reservas", headers=normal, json=body)).status_code == 201

    ultimo = {**_reserva_body(p, vehiculo, inicio), "espacio_id": plazas[9]["id"]}
    res = await client.post(f"{API}/reservas", headers=normal, json=ultimo)
    assert res.status_code == 409 and "Afiliado" in res.json()["detail"]

    afiliado, vehiculo_af = await _setup_usuario(client, "vip@example.com")
    await _afiliar(client, afiliado)
    res = await client.post(f"{API}/reservas", headers=afiliado, json={**ultimo, "vehiculo_id": vehiculo_af})
    assert res.status_code == 201


async def test_alerta_de_cupo_y_notificaciones(client):
    p = await _setup_parqueadero(client)
    ocupante, vehiculo = await _setup_usuario(client)
    interesado, _ = await _setup_usuario(client, "vip@example.com")

    # Solo afiliados crean alertas
    alerta = {"sede_id": p["sede_id"], "tipo": "carro"}
    assert (await client.post(f"{API}/alertas", headers=interesado, json=alerta)).status_code == 403
    await _afiliar(client, interesado)
    assert (await client.post(f"{API}/alertas", headers=interesado, json=alerta)).status_code == 201
    assert len((await client.get(f"{API}/alertas", headers=interesado)).json()) == 1

    r = (await client.post(f"{API}/reservas", headers=ocupante, json=_reserva_body(p, vehiculo, datetime.now(timezone.utc)))).json()
    await client.post(f"{API}/reservas/{r['id']}/entrada", headers=p["admin"])
    await client.post(f"{API}/reservas/{r['id']}/salida", headers=ocupante)

    [aviso] = (await client.get(f"{API}/notificaciones", headers=interesado)).json()
    assert aviso["titulo"] == "¡Se liberó un cupo!" and not aviso["leida"]
    assert (await client.get(f"{API}/reservas/mias/resumen", headers=interesado)).json()["notificaciones_no_leidas"] == 1
    await client.post(f"{API}/notificaciones/{aviso['id']}/leer", headers=interesado)
    assert (await client.get(f"{API}/notificaciones", headers=interesado, params={"no_leidas": True})).json() == []

    # El ocupante recibió la confirmación de su reserva (al registrar la entrada no; al confirmar sí)
    r2 = (await client.post(f"{API}/reservas", headers=ocupante, json=_reserva_body(p, vehiculo, datetime.now(timezone.utc) + timedelta(hours=3)))).json()
    await client.post(f"{API}/reservas/{r2['id']}/confirmar", headers=p["admin"])
    titulos = [n["titulo"] for n in (await client.get(f"{API}/notificaciones", headers=ocupante)).json()]
    assert titulos == ["¡Reserva confirmada!"]


async def test_interesados_en_sede_y_plaza(client):
    p = await _setup_parqueadero(client)
    usuario, _ = await _setup_usuario(client)

    await client.post(f"{API}/sedes/{p['sede_id']}/interes", headers=usuario, json={"espacio_id": p["espacio_id"]})
    await client.post(f"{API}/sedes/{p['sede_id']}/interes", headers=usuario, json={"espacio_id": p["espacio_id"]})  # renueva, no suma
    res = await client.post(f"{API}/sedes/{p['sede_id']}/interes", json={"dispositivo_id": "invitado-123"})
    assert res.json() == {"sede_id": p["sede_id"], "viendo": 2, "por_espacio": {p["espacio_id"]: 1}}

    [sede] = (await client.get(f"{API}/parqueaderos/cercanos", params={"latitud": 10.42, "longitud": -75.545})).json()
    assert sede["interesados"] == 2
    ahora = datetime.now(timezone.utc)
    [plaza] = (await client.get(f"{API}/espacios/plazas", params={
        "sede_id": p["sede_id"], "fecha_inicio": ahora.isoformat(), "fecha_fin": (ahora + timedelta(hours=1)).isoformat(),
    })).json()
    assert plaza["interesados"] == 1


async def test_vencer_reservas_pendientes(client, db):
    p = await _setup_parqueadero(client)
    usuario, vehiculo = await _setup_usuario(client)
    afiliado, vehiculo_af = await _setup_usuario(client, "vip@example.com")
    await _afiliar(client, afiliado)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    sin_pagar = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo, inicio))).json()
    abonada = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo, inicio + timedelta(hours=3)))).json()
    await client.post(f"{API}/reservas/{abonada['id']}/pagos", headers=usuario, json={"monto": 1000, "metodo_pago": "app"})
    del_afiliado = (await client.post(f"{API}/reservas", headers=afiliado, json=_reserva_body(p, vehiculo_af, inicio + timedelta(hours=6)))).json()

    hub = HubTiempoReal()
    assert await vencer_reservas_pendientes(db, hub) == 0  # recién creadas
    assert await vencer_reservas_pendientes(db, hub, ahora=utcnow() + timedelta(minutes=20)) == 1
    estado = lambda r: client.get(f"{API}/reservas/{r['id']}", headers=usuario if r is not del_afiliado else afiliado)
    assert (await estado(sin_pagar)).json()["estado"] == "cancelada"
    assert (await estado(abonada)).json()["estado"] == "pendiente"  # tiene un abono: no se cancela sola
    assert (await estado(del_afiliado)).json()["estado"] == "pendiente"  # afiliado: 60 min
    assert await vencer_reservas_pendientes(db, hub, ahora=utcnow() + timedelta(minutes=61)) == 1
    avisos = [n["titulo"] for n in (await client.get(f"{API}/notificaciones", headers=usuario)).json()]
    assert avisos == ["Reserva vencida"]


async def test_vencer_suscripciones(client, db):
    renueva, _ = await _setup_usuario(client)
    no_renueva, _ = await _setup_usuario(client, "b@example.com")
    s1 = await _afiliar(client, renueva)
    await client.post(f"{API}/suscripciones", headers=no_renueva, json={"renovacion_automatica": False})

    assert await vencer_suscripciones(db, ahora=utcnow() + timedelta(days=31)) == 2
    s1_nueva = (await client.get(f"{API}/suscripciones/mia", headers=renueva)).json()
    assert s1_nueva["fecha_fin"] > s1["fecha_fin"] and s1_nueva["estado"] == "activa"
    assert (await client.get(f"{API}/suscripciones/mia", headers=no_renueva)).json() is None


class _SocketFalso:
    def __init__(self):
        self.mensajes = []

    async def accept(self):
        pass

    async def send_json(self, mensaje):
        self.mensajes.append(mensaje)


async def test_hub_reparte_eventos_entre_procesos_con_redis():
    servidor = fakeredis.FakeServer()
    proceso_a, proceso_b = HubTiempoReal(), HubTiempoReal()
    await proceso_a.iniciar(cliente=fakeredis.aioredis.FakeRedis(server=servidor, decode_responses=True))
    await proceso_b.iniciar(cliente=fakeredis.aioredis.FakeRedis(server=servidor, decode_responses=True))
    cliente_en_b, cliente_otra_sede = _SocketFalso(), _SocketFalso()
    await proceso_b.conectar("sede1", cliente_en_b)
    await proceso_b.conectar("sede2", cliente_otra_sede)
    await asyncio.sleep(0.05)  # que las suscripciones queden listas

    await proceso_a.publicar("sede1", {"evento": "check_in", "espacio_id": "e1"})
    for _ in range(50):
        if cliente_en_b.mensajes:
            break
        await asyncio.sleep(0.02)
    assert cliente_en_b.mensajes == [{"evento": "check_in", "espacio_id": "e1"}]
    assert cliente_otra_sede.mensajes == []
    await proceso_a.detener()
    await proceso_b.detener()


async def test_hub_sin_redis_envia_local():
    hub = HubTiempoReal()
    await hub.iniciar(None)
    socket = _SocketFalso()
    await hub.conectar("s", socket)
    await hub.publicar("s", {"evento": "pago"})
    assert socket.mensajes == [{"evento": "pago"}]
