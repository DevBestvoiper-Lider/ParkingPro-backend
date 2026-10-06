import re
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_parkingpro import API, _iso, _reserva_body, _setup_parqueadero, _setup_usuario

pytestmark = pytest.mark.asyncio

# Sedes de prueba en _setup_parqueadero: centro de Cartagena (10.4236, -75.5478)
CERCA = {"latitud": 10.4200, "longitud": -75.5450}  # ~0.5 km
LEJOS = {"latitud": 10.3910, "longitud": -75.4794}  # ~8 km (aeropuerto)


async def test_mapa_parqueaderos_cercanos(client):
    p = await _setup_parqueadero(client)

    res = await client.get(f"{API}/parqueaderos/cercanos", params={**CERCA, "radio_km": 2, "tipo": "carro"})
    assert res.status_code == 200, res.text
    [sede] = res.json()
    assert sede["sede_id"] == p["sede_id"]
    assert sede["parqueadero_nombre"] == "ParkingPro Centro"
    assert 0 < sede["distancia_km"] < 1
    assert sede["precio_hora_desde"] == 4500
    assert sede["espacios_libres"] == 1
    assert sede["espacios_total"] == 1
    assert (sede["latitud"], sede["longitud"]) == (10.4236, -75.5478)

    assert (await client.get(f"{API}/parqueaderos/cercanos", params={**LEJOS, "radio_km": 2})).json() == []
    assert (await client.get(f"{API}/parqueaderos/cercanos", params={**CERCA, "q": "chapinero"})).json() != []
    assert (await client.get(f"{API}/parqueaderos/cercanos", params={**CERCA, "q": "zona rosa"})).json() == []

    # La sede expone sus coordenadas
    parqueadero = (await client.get(f"{API}/parqueaderos/{p['parqueadero']['id']}")).json()
    assert parqueadero["sedes"][0]["latitud"] == 10.4236


async def test_libres_descuenta_reservas_inmediatas(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    ahora = datetime.now(timezone.utc)
    await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora + timedelta(minutes=10)))

    [sede] = (await client.get(f"{API}/parqueaderos/cercanos", params=CERCA)).json()
    assert sede["espacios_libres"] == 0


async def test_coordenadas_van_juntas(client):
    p = await _setup_parqueadero(client, nit="900-9", admin_email="a9@p.com")
    res = await client.post(f"{API}/parqueaderos/{p['parqueadero']['id']}/sedes", headers=p["admin"], json={
        "nombre": "Sin longitud", "direccion": "X", "ciudad": "Cartagena", "latitud": 10.4,
    })
    assert res.status_code == 422


async def test_grilla_de_plazas_por_horario(client):
    p = await _setup_parqueadero(client)
    admin = p["admin"]
    for codigo, estado in (("A-13", "disponible"), ("A-14", "mantenimiento")):
        await client.post(f"{API}/espacios", headers=admin, json={
            "sede_id": p["sede_id"], "codigo": codigo, "zona": "Zona A", "tipo": "carro", "estado": estado,
        })
    usuario, vehiculo_id = await _setup_usuario(client)
    ahora = datetime.now(timezone.utc)

    # A-12 reservada de ahora a +2h, y con el carro adentro
    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora))).json()["id"]
    await client.post(f"{API}/reservas/{rid}/entrada", headers=admin)

    async def estados(inicio, horas=1):
        res = await client.get(f"{API}/espacios/plazas", params={
            "sede_id": p["sede_id"], "fecha_inicio": _iso(inicio), "fecha_fin": _iso(inicio + timedelta(hours=horas)),
        })
        assert res.status_code == 200, res.text
        return {pl["codigo"]: pl["estado_horario"] for pl in res.json()}

    assert await estados(ahora) == {"A-12": "ocupada", "A-13": "disponible", "A-14": "mantenimiento"}
    assert (await estados(ahora + timedelta(hours=1)))["A-12"] == "reservada"
    assert (await estados(ahora + timedelta(hours=5)))["A-12"] == "disponible"

    zona_a = await client.get(f"{API}/espacios/plazas", params={
        "sede_id": p["sede_id"], "zona": "Zona A", "fecha_inicio": _iso(ahora), "fecha_fin": _iso(ahora + timedelta(hours=1)),
    })
    assert {pl["codigo"] for pl in zona_a.json()} == {"A-13", "A-14"}


async def test_codigo_y_datos_para_mostrar(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)

    r1 = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()
    r2 = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio + timedelta(hours=3)))).json()
    assert re.fullmatch(r"Rsv-\d{6}", r1["codigo"])
    assert int(r2["codigo"][4:]) == int(r1["codigo"][4:]) + 1
    assert r1["sede_nombre"] == "Sede Chapinero"
    assert r1["parqueadero_nombre"] == "ParkingPro Centro"
    assert r1["espacio_codigo"] == "A-12"
    assert r1["placa"] == "ABC123"
    assert r1["cliente_nombre"] == "Carlos"

    # El empleado busca por código
    res = await client.get(f"{API}/reservas", headers=p["admin"], params={"codigo": r2["codigo"]})
    assert [r["id"] for r in res.json()] == [r2["id"]]


async def test_pestanas_mis_reservas(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    activa = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()
    cancelada = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio + timedelta(hours=3)))).json()
    await client.post(f"{API}/reservas/{cancelada['id']}/cancelar", headers=usuario)

    proximas = await client.get(f"{API}/reservas/mias", headers=usuario, params=[("estado", "pendiente"), ("estado", "confirmada")])
    assert [r["id"] for r in proximas.json()] == [activa["id"]]
    canceladas = await client.get(f"{API}/reservas/mias", headers=usuario, params={"estado": "cancelada"})
    assert [r["id"] for r in canceladas.json()] == [cancelada["id"]]


async def test_prepago_confirma_la_reserva(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    r = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()

    # Un abono parcial no confirma
    r = (await client.post(f"{API}/reservas/{r['id']}/pagos", headers=usuario, json={"monto": 4500, "metodo_pago": "app"})).json()
    assert r["estado"] == "pendiente"
    # Completar el total estimado sí
    r = (await client.post(f"{API}/reservas/{r['id']}/pagos", headers=usuario, json={"monto": 4500, "metodo_pago": "app"})).json()
    assert r["estado"] == "confirmada"
    assert r["saldo"] == 0


async def test_editar_y_eliminar_vehiculo(client):
    headers, vid = await _setup_usuario(client)

    res = await client.patch(f"{API}/usuarios/me/vehiculos/{vid}", headers=headers, json={
        "placa": "xyz 789", "marca": "Kia", "modelo": "Rio", "color": "Rojo",
    })
    assert res.status_code == 200, res.text
    vehiculo = res.json()["vehiculos"][0]
    assert vehiculo["id"] == vid
    assert vehiculo["placa"] == "XYZ789"
    assert (vehiculo["marca"], vehiculo["modelo"], vehiculo["color"]) == ("Kia", "Rio", "Rojo")

    res = await client.delete(f"{API}/usuarios/me/vehiculos/{vid}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["vehiculos"] == []


async def test_usuario_finaliza_su_sesion_y_resumen_home(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    otro, _ = await _setup_usuario(client, "otro@example.com")
    ahora = datetime.now(timezone.utc)

    resumen = (await client.get(f"{API}/reservas/mias/resumen", headers=usuario)).json()
    assert resumen == {
        "reservas_proximas": 0, "vehiculos": 1, "sesion_activa": None, "plan": "por_uso", "notificaciones_no_leidas": 0,
    }

    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora))).json()["id"]
    assert (await client.get(f"{API}/reservas/mias/resumen", headers=usuario)).json()["reservas_proximas"] == 1

    await client.post(f"{API}/reservas/{rid}/entrada", headers=p["admin"])
    resumen = (await client.get(f"{API}/reservas/mias/resumen", headers=usuario)).json()
    assert resumen["reservas_proximas"] == 0
    sesion = resumen["sesion_activa"]
    assert sesion["id"] == rid and sesion["sesion"]["estado"] == "activa"
    assert sesion["total"] == 4500  # recién entró: mínimo 1 hora, no las 2 reservadas
    assert sesion["espacio_codigo"] == "A-12"

    # Otro usuario no puede cerrarla; el dueño sí
    assert (await client.post(f"{API}/reservas/{rid}/salida", headers=otro)).status_code == 404
    res = await client.post(f"{API}/reservas/{rid}/salida", headers=usuario)
    assert res.status_code == 200, res.text
    assert res.json()["estado"] == "completada"
    assert (await client.get(f"{API}/espacios/{p['espacio_id']}")).json()["estado"] == "disponible"
    assert (await client.get(f"{API}/reservas/mias/resumen", headers=usuario)).json()["sesion_activa"] is None


async def test_reservar_despues_de_una_sesion_activa(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    otro, otro_vehiculo = await _setup_usuario(client, "otro@example.com")
    ahora = datetime.now(timezone.utc)

    # Carlos reservó de -30 min a +30 min y ya está adentro
    body = _reserva_body(p, vehiculo_id, ahora - timedelta(minutes=30), horas=1)
    rid = (await client.post(f"{API}/reservas", headers=usuario, json=body)).json()["id"]
    await client.post(f"{API}/reservas/{rid}/entrada", headers=p["admin"])

    # Un horario que empieza cuando termina la reserva de Carlos sí se puede reservar
    res = await client.post(f"{API}/reservas", headers=otro, json=_reserva_body(p, otro_vehiculo, ahora + timedelta(minutes=31), horas=1))
    assert res.status_code == 201
    # Uno que se cruza, no
    res = await client.post(f"{API}/reservas", headers=otro, json=_reserva_body(p, otro_vehiculo, ahora, horas=1))
    assert res.status_code == 409
