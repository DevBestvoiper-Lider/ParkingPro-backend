from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from bson import Decimal128, ObjectId

from app.core.utils import hoy_local, inicio_dia_utc
from app.services.actividad_usuario import calcular_actividad
from tests.test_afiliados_tiempo_real import _afiliar
from tests.test_parkingpro import API, _reserva_body, _setup_parqueadero, _setup_usuario


def _cuando(meses_atras: int):
    dia = hoy_local().replace(day=1)
    for _ in range(meses_atras):
        dia = (dia - timedelta(days=1)).replace(day=1)
    return inicio_dia_utc(dia) + timedelta(hours=15)


def _pago(monto: str, cuando, estado: str = "pagado"):
    return {
        "monto": Decimal128(Decimal(monto)),
        "fecha_pago": cuando,
        "estado": estado,
        "metodo_pago": "app",
    }


def _visita(sede, nombre, vehiculo, placa, cuando, valor="4500", descuento=None, pagos=None, estado="completada"):
    fin = cuando + timedelta(hours=2)
    tarifa = {"nombre": "Hora", "valor_hora": Decimal128(Decimal(valor))}
    if descuento:
        tarifa["descuento_pct"] = descuento
    doc = {
        "estado": estado,
        "sede_id": sede,
        "sede_nombre": nombre,
        "vehiculo_id": vehiculo,
        "placa": placa,
        "tarifa_aplicada": tarifa,
        "fecha_inicio": cuando,
        "fecha_fin": fin,
        "pagos": pagos or [],
    }
    if estado == "completada":
        doc["sesion"] = {"hora_entrada": cuando, "hora_salida": fin, "estado": "finalizada"}
    return doc


def test_calcular_actividad_vacia():
    vacia = calcular_actividad([])
    assert vacia["total_gastado"] == Decimal("0.00")
    assert len(vacia["gasto_por_mes"]) == 6
    assert vacia["tendencia_pct"] is None
    assert vacia["reservas_completadas"] == 0
    assert vacia["promedio_por_visita"] == Decimal("0.00")
    assert vacia["ahorro_afiliado"] == Decimal("0.00")
    assert vacia["ahorro_es_estimado"] is True


def test_calcular_actividad_tendencia_ahorro_y_ranking():
    actual, anterior = _cuando(0), _cuando(1)
    centro, boca = ObjectId(), ObjectId()
    carro, moto = ObjectId(), ObjectId()
    reservas = [
        # 2 h con 15 % ya aplicado: cobra 7650, el ahorro real es 1350.
        _visita(centro, "Centro", carro, "ABC123", actual, valor="3825", descuento=15, pagos=[_pago("7650", actual)]),
        _visita(centro, "Centro", carro, "ABC123", anterior, pagos=[_pago("8000", anterior), _pago("1000", anterior, "reembolsado")]),
        _visita(boca, "Bocagrande", moto, "MOTO1", actual, pagos=[_pago("9000", actual)]),
        _visita(boca, "Bocagrande", moto, "MOTO1", actual, estado="cancelada"),
    ]
    act = calcular_actividad(reservas)

    assert act["reservas_completadas"] == 3
    assert act["reservas_canceladas"] == 1
    assert act["total_gastado"] == Decimal("23650.00")  # 7650 + 8000 - 1000 + 9000
    assert act["gasto_por_mes"][-1]["total"] == Decimal("16650.00")
    assert act["gasto_por_mes"][-2]["total"] == Decimal("7000.00")
    assert act["tendencia_pct"] == 137.9  # (16650 - 7000) / 7000
    assert act["horas_estacionado"] == 6.0
    assert act["promedio_por_visita"] == Decimal("8550.00")  # (7650 + 9000 + 9000) / 3
    assert act["ahorro_afiliado"] == Decimal("1350.00")
    assert act["ahorro_es_estimado"] is False
    assert [(s["nombre"], s["visitas"]) for s in act["sedes_mas_usadas"]] == [("Centro", 2), ("Bocagrande", 1)]
    assert act["vehiculos_mas_usados"][0] == {"id": str(carro), "nombre": "ABC123", "visitas": 2}


def test_sin_descuento_el_ahorro_es_lo_que_habria_ahorrado():
    cuando = _cuando(0)
    reserva = _visita(ObjectId(), "Centro", ObjectId(), "ABC123", cuando, pagos=[_pago("4500", cuando)])
    reserva["sesion"]["hora_salida"] = reserva["sesion"]["hora_entrada"] + timedelta(hours=1)
    act = calcular_actividad([reserva])
    assert act["ahorro_es_estimado"] is True
    assert act["ahorro_afiliado"] == Decimal("675.00")  # 4500 × 15 %


@pytest.mark.asyncio
async def test_endpoint_mi_actividad(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    ahora = datetime.now(timezone.utc)

    vacia = await client.get(f"{API}/reservas/mias/actividad", headers=usuario)
    assert vacia.status_code == 200, vacia.text
    assert vacia.json()["reservas_completadas"] == 0
    assert (await client.get(f"{API}/reservas/mias/actividad")).status_code == 401

    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora))).json()["id"]
    await client.post(f"{API}/reservas/{rid}/entrada", headers=p["admin"])
    await client.post(f"{API}/reservas/{rid}/pagos", headers=usuario, json={"monto": 4500, "metodo_pago": "app"})
    assert (await client.post(f"{API}/reservas/{rid}/salida", headers=usuario)).status_code == 200

    cancelada = (await client.post(
        f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora + timedelta(hours=3)),
    )).json()["id"]
    await client.post(f"{API}/reservas/{cancelada}/cancelar", headers=usuario)

    act = (await client.get(f"{API}/reservas/mias/actividad", headers=usuario)).json()
    assert act["reservas_completadas"] == 1
    assert act["reservas_canceladas"] == 1
    assert act["total_gastado"] == 4500
    assert act["promedio_por_visita"] == 4500
    assert act["gasto_por_mes"][-1]["total"] == 4500
    assert act["tendencia_pct"] is None
    assert act["ahorro_es_estimado"] is True
    assert act["ahorro_afiliado"] == 675
    assert act["sedes_mas_usadas"] == [{"id": p["sede_id"], "nombre": "Sede Chapinero", "visitas": 1}]
    assert act["vehiculos_mas_usados"][0]["nombre"] == "ABC123"
    assert act["vehiculos_mas_usados"][0]["visitas"] == 1


@pytest.mark.asyncio
async def test_ahorro_real_de_afiliado(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    await _afiliar(client, usuario)
    ahora = datetime.now(timezone.utc)

    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, ahora, horas=1))).json()["id"]
    await client.post(f"{API}/reservas/{rid}/entrada", headers=p["admin"])
    pagado = (await client.post(f"{API}/reservas/{rid}/pagos", headers=usuario, json={"monto": 3825, "metodo_pago": "app"})).json()
    assert pagado["tarifa_aplicada"]["descuento_pct"] == 15
    await client.post(f"{API}/reservas/{rid}/salida", headers=usuario)

    act = (await client.get(f"{API}/reservas/mias/actividad", headers=usuario)).json()
    assert act["ahorro_es_estimado"] is False
    assert act["ahorro_afiliado"] == 675
    assert act["total_gastado"] == 3825
