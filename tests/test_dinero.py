from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.services.liquidacion_service import LiquidacionService
from tests.test_afiliados_tiempo_real import _afiliar
from tests.test_app_movil import CERCA
from tests.test_parkingpro import API, _login, _reserva_body, _setup_parqueadero, _setup_usuario

pytestmark = pytest.mark.asyncio


async def _parqueadero_de_10000(client, db, en_prueba=False):
    """Una reserva de 2 h a $5.000 = $10.000. Fuera de prueba cobra la comisión del socio (10 %)."""
    p = await _setup_parqueadero(client)
    res = await client.post(f"{API}/tarifas", headers=p["admin"], json={
        "sede_id": p["sede_id"], "nombre": "Carro 5000", "tipo_vehiculo": "carro", "valor_hora": 5000,
    })
    p["tarifa_id"] = res.json()["id"]
    pid = ObjectId(p["parqueadero"]["id"])
    if not en_prueba:
        await db["parqueaderos"].update_one({"_id": pid}, {"$set": {"condiciones.prueba_hasta": datetime(2020, 1, 1)}})
    p["socio"] = await _login(client, "socios", "socio.admin@p.com")
    return p


async def _reservar(client, p, usuario, vehiculo_id):
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    res = await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))
    assert res.status_code == 201, res.text
    return res.json()


async def test_condiciones_pactadas_al_crear(client, db):
    p = await _setup_parqueadero(client)
    socio = await db["socios"].find_one({"email": "socio.admin@p.com"})
    assert socio["condiciones"] == {"comision_pct": 10, "limite_deuda": 500000, "dias_gracia": 7, "politica": "defecto"}
    assert socio["liquida_desde"] == socio["fecha_registro"]
    parqueadero = await db["parqueaderos"].find_one({"_id": ObjectId(p["parqueadero"]["id"])})
    assert parqueadero["condiciones"]["comision_prueba_pct"] == 0
    dias = (parqueadero["condiciones"]["prueba_hasta"] - parqueadero["fecha_registro"]).days
    assert dias == 30


async def test_reembolso_conserva_la_comision(client, db):
    p = await _parqueadero_de_10000(client, db)
    usuario, vehiculo_id = await _setup_usuario(client)
    r = await _reservar(client, p, usuario, vehiculo_id)
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=usuario, json={"monto": 10000, "metodo_pago": "app"})
    await client.post(f"{API}/reservas/{r['id']}/cancelar", headers=p["admin"])
    res = await client.post(f"{API}/reservas/{r['id']}/reembolsos", headers=p["admin"], json={"monto": 10000, "metodo_pago": "app"})
    assert res.status_code == 201, res.text
    assert res.json()["saldo"] == 0  # el usuario queda en $0

    pagos = (await db["reservas"].find_one({"_id": ObjectId(r["id"])}))["pagos"]
    assert [(x["estado"], x["comision_pct"], x["comision"].to_decimal()) for x in pagos] == [
        ("pagado", 10, 1000), ("reembolsado", 10, 0),
    ]
    assert "comision" not in res.json()["pagos"][0]  # la comisión no se le muestra al cliente

    cuenta = (await client.get(f"{API}/socios/me/cuenta", headers=p["socio"])).json()
    assert (cuenta["pagos_app"], cuenta["comision_app"], cuenta["reembolsos_app"]) == (10000, 1000, 10000)
    assert cuenta["total"] == -1000 and cuenta["deuda"] == 1000  # el socio en −$1.000, ParkingPro en +$1.000
    assert cuenta["comision_pct"] == 10 and cuenta["uso_limite_pct"] == 0


async def test_afiliado_compensado_y_prueba_sin_comision(client, db):
    p = await _parqueadero_de_10000(client, db, en_prueba=True)
    usuario, vehiculo_id = await _setup_usuario(client)
    await _afiliar(client, usuario)
    r = await _reservar(client, p, usuario, vehiculo_id)
    assert r["total"] == 8500  # 15 % menos
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=usuario, json={"monto": 8500, "metodo_pago": "app"})

    cuenta = (await client.get(f"{API}/socios/me/cuenta", headers=p["socio"])).json()
    assert cuenta["comision_app"] == 0  # en prueba
    assert cuenta["compensacion"] == 1500  # ParkingPro pone el descuento: el socio recibe la tarifa completa
    assert cuenta["total"] == 10000


async def test_deuda_suspende_y_reactiva(client, db):
    p = await _parqueadero_de_10000(client, db)
    pid = ObjectId(p["parqueadero"]["id"])
    await db["socios"].update_one({"email": "socio.admin@p.com"}, {"$set": {"condiciones.limite_deuda": 1000}})
    usuario, vehiculo_id = await _setup_usuario(client)
    r = await _reservar(client, p, usuario, vehiculo_id)
    res = await client.post(f"{API}/reservas/{r['id']}/pagos", headers=p["admin"], json={"monto": 10000, "metodo_pago": "efectivo"})
    assert res.json()["estado"] == "confirmada"

    servicio = LiquidacionService.de(db)

    async def revisar(ahora):
        await servicio.revisar_deuda(await db["socios"].find_one({"email": "socio.admin@p.com"}), ahora)
        return (await db["parqueaderos"].find_one({"_id": pid}))["estado"]

    # Cobró en caja: debe la comisión. Llega al 100 % del límite, pero tiene días de gracia.
    ahora = datetime.now(timezone.utc)
    assert await revisar(ahora) == "en_prueba"
    socio = await db["socios"].find_one({"email": "socio.admin@p.com"})
    assert socio["deuda"]["aviso_pct"] == 100 and "excedida_desde" in socio["deuda"]

    # Pasada la gracia se suspende: no sale en el mapa ni recibe reservas, y conserva las confirmadas
    assert await revisar(ahora + timedelta(days=8)) == "suspendido"
    assert (await client.get(f"{API}/parqueaderos/cercanos", params=CERCA)).json() == []
    res = await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora + timedelta(hours=5)))
    assert res.status_code == 409
    assert (await client.get(f"{API}/reservas/{r['id']}", headers=usuario)).json()["estado"] == "confirmada"

    # Las semanas cerradas se liquidaron y el saldo se fue trasladando a la última
    liquidaciones = (await client.get(f"{API}/socios/me/liquidaciones", headers=p["socio"])).json()
    assert liquidaciones and liquidaciones[0]["estado"] == "pendiente" and liquidaciones[0]["total"] == -1000
    assert all(x["estado"] == "trasladada" for x in liquidaciones[1:])
    cuenta = await servicio.estado_de_cuenta(socio, ahora + timedelta(days=8))
    assert cuenta["saldo_anterior"] == cuenta["total"] == -1000 and cuenta["comision_caja"] == 0

    # Con un límite mayor vuelve a su estado anterior
    await db["socios"].update_one({"_id": socio["_id"]}, {"$set": {"condiciones.limite_deuda": 5000}})
    assert await revisar(ahora + timedelta(days=9)) == "en_prueba"
    assert (await client.get(f"{API}/parqueaderos/cercanos", params=CERCA)).json() != []
    socio = await db["socios"].find_one({"_id": socio["_id"]})
    assert socio["deuda"] == {}
    historial = await db["auditoria"].find({"entidad_id": pid, "actor.tipo": "sistema"}).sort("fecha", 1).to_list(None)
    assert [x["despues"]["estado"] for x in historial] == ["suspendido", "en_prueba"]


async def test_socio_no_migrado_no_se_suspende(client, db):
    p = await _parqueadero_de_10000(client, db)
    await db["socios"].update_one({"email": "socio.admin@p.com"}, {"$unset": {"condiciones": ""}})
    usuario, vehiculo_id = await _setup_usuario(client)
    r = await _reservar(client, p, usuario, vehiculo_id)
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=p["admin"], json={"monto": 10000, "metodo_pago": "efectivo"})
    await LiquidacionService.de(db).correr(datetime.now(timezone.utc) + timedelta(days=30))
    assert (await db["parqueaderos"].find_one({"_id": ObjectId(p["parqueadero"]["id"])}))["estado"] == "en_prueba"
