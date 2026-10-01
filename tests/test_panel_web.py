from datetime import datetime, timedelta, timezone

import pytest

from tests.test_parkingpro import API, _reserva_body, _setup_parqueadero, _setup_usuario

pytestmark = pytest.mark.asyncio


async def _plazas(client, p, n, zona="Zona A", tipo="carro", prefijo="A"):
    for i in range(n):
        await client.post(f"{API}/espacios", headers=p["admin"], json={
            "sede_id": p["sede_id"], "codigo": f"{prefijo}-{i + 20}", "zona": zona, "tipo": tipo,
        })


async def test_check_in_y_check_out_manual_por_placa(client):
    p = await _setup_parqueadero(client)
    admin = p["admin"]

    # Vehículo sin cuenta en la app: se crea un cliente ocasional
    res = await client.post(f"{API}/reservas/check-in-manual", headers=admin, json={
        "sede_id": p["sede_id"], "placa": "xyz-789", "horas_estimadas": 2, "nombre_cliente": "Pedro",
    })
    assert res.status_code == 201, res.text
    r = res.json()
    assert r["placa"] == "XYZ789" and r["cliente_nombre"] == "Pedro"
    assert r["estado"] == "confirmada" and r["sesion"]["estado"] == "activa"
    assert r["espacio_codigo"] == "A-12" and r["tarifa_aplicada"]["valor_hora"] == 4500

    # No puede entrar dos veces, y ya no quedan plazas de carro
    res = await client.post(f"{API}/reservas/check-in-manual", headers=admin, json={"sede_id": p["sede_id"], "placa": "XYZ789"})
    assert res.status_code == 409
    res = await client.post(f"{API}/reservas/check-in-manual", headers=admin, json={"sede_id": p["sede_id"], "placa": "AAA111"})
    assert res.status_code == 409

    res = await client.post(f"{API}/reservas/check-out-manual", headers=admin, json={"placa": "XYZ 789"})
    assert res.status_code == 200, res.text
    assert res.json()["estado"] == "completada"
    assert (await client.post(f"{API}/reservas/check-out-manual", headers=admin, json={"placa": "XYZ789"})).status_code == 404

    # Un usuario registrado se reconoce por su placa
    usuario, _ = await _setup_usuario(client)
    r = (await client.post(f"{API}/reservas/check-in-manual", headers=admin, json={"sede_id": p["sede_id"], "placa": "ABC123"})).json()
    assert r["cliente_nombre"] == "Carlos"
    mias = (await client.get(f"{API}/reservas/mias", headers=usuario)).json()
    assert [m["id"] for m in mias] == [r["id"]]


async def test_busqueda_de_reservas(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    r = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()

    async def buscar(**params):
        res = await client.get(f"{API}/reservas", headers=p["admin"], params=params)
        assert res.status_code == 200, res.text
        return [x["id"] for x in res.json()]

    assert await buscar(q="abc 123") == [r["id"]]
    assert await buscar(q="carl") == [r["id"]]
    assert await buscar(q=r["codigo"].lower()) == [r["id"]]
    assert await buscar(q="zzz") == []
    assert await buscar(zona="Zona A") == []  # el espacio A-12 no tiene zona


async def test_pagos_reembolsos_y_resumen(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)
    r = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=usuario, json={"monto": 9000, "metodo_pago": "app"})
    r = (await client.post(f"{API}/reservas/{r['id']}/cancelar", headers=p["admin"])).json()
    assert r["saldo"] == -9000  # pagó y se canceló: hay que devolver

    # Operador no puede reembolsar; admin sí, hasta lo pagado
    await client.post(f"{API}/empleados", headers=p["admin"], json={"nombre": "Op", "email": "op@p.com", "password": "secreto123"})
    res = await client.post(f"{API}/auth/empleados/login", data={"username": "op@p.com", "password": "secreto123"})
    operador = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert (await client.post(f"{API}/reservas/{r['id']}/reembolsos", headers=operador, json={"monto": 9000, "metodo_pago": "app"})).status_code == 403
    assert (await client.post(f"{API}/reservas/{r['id']}/reembolsos", headers=p["admin"], json={"monto": 9001, "metodo_pago": "app"})).status_code == 422
    res = await client.post(f"{API}/reservas/{r['id']}/reembolsos", headers=p["admin"], json={"monto": 9000, "metodo_pago": "app"})
    assert res.status_code == 201, res.text
    assert res.json()["saldo"] == 0 and res.json()["total_pagado"] == 0

    pagos = (await client.get(f"{API}/admin/pagos", headers=p["admin"])).json()
    assert [(x["estado"], x["monto"]) for x in pagos] == [("reembolsado", 9000), ("pagado", 9000)]
    assert pagos[1]["codigo"].startswith("TX-") and pagos[1]["placa"] == "ABC123"
    assert pagos[1]["reserva_codigo"] == r["codigo"]

    resumen = (await client.get(f"{API}/admin/pagos/resumen", headers=p["admin"])).json()
    assert resumen["recaudado"] == 0
    assert resumen["transacciones"] == 2
    assert (resumen["reembolsos_cantidad"], resumen["reembolsos_monto"]) == (1, 9000)
    assert resumen["metodos"] == [{"metodo_pago": "app", "monto": 9000, "porcentaje": 100.0}]
    assert resumen["ticket_promedio"] == 9000

    csv = await client.get(f"{API}/admin/pagos/exportar", headers=p["admin"])
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.lstrip("﻿").splitlines()[0] == "transaccion,reserva,cliente,placa,metodo,monto,estado,fecha"
    assert len(csv.text.splitlines()) == 3


async def test_dashboard_estadisticas_y_actividad(client):
    p = await _setup_parqueadero(client)
    await _plazas(client, p, 3)
    await client.patch(f"{API}/espacios/{p['espacio_id']}", headers=p["admin"], json={"estado": "mantenimiento"})
    usuario, vehiculo_id = await _setup_usuario(client)
    plazas = (await client.get(f"{API}/espacios", headers=p["admin"], params={"sede_id": p["sede_id"], "zona": "Zona A"})).json()

    ahora = datetime.now(timezone.utc)
    body = _reserva_body(p, vehiculo_id, ahora)
    body["espacio_id"] = plazas[0]["id"]
    res = await client.post(f"{API}/reservas", headers=usuario, json=body)
    assert res.status_code == 201, res.text
    r = res.json()
    await client.post(f"{API}/reservas/{r['id']}/entrada", headers=p["admin"])
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=p["admin"], json={"monto": 4500, "metodo_pago": "efectivo"})
    body = _reserva_body(p, vehiculo_id, ahora + timedelta(minutes=30))
    body["espacio_id"] = plazas[1]["id"]
    await client.post(f"{API}/reservas", headers=usuario, json=body)

    res = await client.get(f"{API}/admin/dashboard", headers=p["admin"])
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["plazas"] == {"total": 4, "disponibles": 1, "ocupadas": 1, "reservadas": 1, "mantenimiento": 1}
    assert d["ingresos_hoy"] == 4500 and d["ingresos_ayer"] == 0 and d["variacion_ingresos_pct"] is None
    assert len(d["ingresos_ultimos_7_dias"]) == 7 and d["ingresos_ultimos_7_dias"][-1]["total"] == 4500
    zona_a = next(z for z in d["ocupacion_por_zona"] if z["zona"] == "Zona A")
    assert (zona_a["total"], zona_a["porcentaje_del_total"], zona_a["porcentaje_ocupacion"]) == (3, 75.0, 66.7)
    assert len(d["proximas_reservas"]) == 1 and d["proximas_reservas"][0]["placa"] == "ABC123"
    tipos = [a["tipo"] for a in d["actividad_reciente"]]
    assert tipos[:3] == ["reserva_creada", "pago", "check_in"] and "espacio_estado" in tipos
    assert {a["tipo"] for a in d["alertas"]} == {"mantenimiento", "pendientes_pago"}

    e = (await client.get(f"{API}/admin/reservas/estadisticas", headers=p["admin"])).json()
    assert (e["total"], e["confirmadas"], e["pendientes"], e["pendientes_de_pago"], e["monto_pendiente"]) == (2, 1, 1, 1, 9000)


async def test_clientes_vehiculos_y_reportes(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    ahora = datetime.now(timezone.utc)
    r = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora))).json()
    await client.post(f"{API}/reservas/{r['id']}/entrada", headers=p["admin"])
    await client.post(f"{API}/reservas/{r['id']}/salida", headers=p["admin"])
    await client.post(f"{API}/reservas/{r['id']}/pagos", headers=p["admin"], json={"monto": 4500, "metodo_pago": "tarjeta"})

    [cliente] = (await client.get(f"{API}/admin/clientes", headers=p["admin"])).json()
    assert (cliente["nombre"], cliente["reservas"], cliente["total_pagado"], cliente["afiliado"]) == ("Carlos", 1, 4500, False)
    assert (await client.get(f"{API}/admin/clientes", headers=p["admin"], params={"q": "abc123"})).json() != []
    assert (await client.get(f"{API}/admin/clientes", headers=p["admin"], params={"q": "maria"})).json() == []

    [vehiculo] = (await client.get(f"{API}/admin/vehiculos", headers=p["admin"])).json()
    assert (vehiculo["placa"], vehiculo["visitas"], vehiculo["adentro"]) == ("ABC123", 1, False)

    rep = (await client.get(f"{API}/admin/reportes", headers=p["admin"])).json()
    assert rep["ingresos_total"] == 4500 and len(rep["ingresos_por_dia"]) == 30
    assert rep["reservas_por_estado"] == {"completada": 1}
    assert rep["ingresos_por_metodo"][0]["metodo_pago"] == "tarjeta"
    assert sum(h["entradas"] for h in rep["horas_pico"]) == 1
    assert rep["duracion_promedio_min"] is not None

    csv = (await client.get(f"{API}/admin/reservas/exportar", headers=p["admin"])).text.lstrip("﻿").splitlines()
    assert csv[0].startswith("codigo,cliente,placa") and "ABC123" in csv[1]

    # Un usuario de la app no entra al panel
    assert (await client.get(f"{API}/admin/dashboard", headers=usuario)).status_code == 403
