from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _login(client, tipo: str, email: str, password: str = "secreto123") -> dict:
    res = await client.post(f"{API}/auth/{tipo}/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def _setup_parqueadero(client, nit="900-1", admin_email="admin@p.com"):
    res = await client.post(f"{API}/parqueaderos", json={
        "nombre": "ParkingPro Centro",
        "nit": nit,
        "email_contacto": "contacto@p.com",
        "administrador": {"nombre": "Laura", "email": admin_email, "password": "secreto123"},
    })
    assert res.status_code == 201, res.text
    parqueadero = res.json()
    admin = await _login(client, "empleados", admin_email)

    res = await client.post(f"{API}/parqueaderos/{parqueadero['id']}/sedes", headers=admin, json={
        "nombre": "Sede Chapinero", "direccion": "Cra 13 # 45-67", "ciudad": "Bogotá",
        "latitud": 10.4236, "longitud": -75.5478,
    })
    assert res.status_code == 201, res.text
    sede_id = res.json()["sedes"][0]["id"]

    res = await client.post(f"{API}/espacios", headers=admin, json={"sede_id": sede_id, "codigo": "A-12", "tipo": "carro"})
    assert res.status_code == 201, res.text
    espacio_id = res.json()["id"]

    res = await client.post(f"{API}/tarifas", headers=admin, json={
        "sede_id": sede_id, "nombre": "Carro diurna", "tipo_vehiculo": "carro", "valor_hora": 4500,
    })
    assert res.status_code == 201, res.text
    assert res.json()["valor_hora"] == 4500
    return {"parqueadero": parqueadero, "admin": admin, "sede_id": sede_id,
            "espacio_id": espacio_id, "tarifa_id": res.json()["id"]}


async def _setup_usuario(client, email="carlos@example.com"):
    res = await client.post(f"{API}/auth/usuarios/registro", json={"nombre": "Carlos", "email": email, "password": "secreto123"})
    assert res.status_code == 201, res.text
    headers = await _login(client, "usuarios", email)
    res = await client.post(f"{API}/usuarios/me/vehiculos", headers=headers, json={"placa": "abc 123", "marca": "Mazda"})
    assert res.status_code == 201, res.text
    vehiculo = res.json()["vehiculos"][0]
    assert vehiculo["placa"] == "ABC123"
    return headers, vehiculo["id"]


def _reserva_body(p, vehiculo_id, inicio, horas=2):
    return {
        "sede_id": p["sede_id"], "espacio_id": p["espacio_id"], "tarifa_id": p["tarifa_id"],
        "vehiculo_id": vehiculo_id, "fecha_inicio": _iso(inicio), "fecha_fin": _iso(inicio + timedelta(hours=horas)),
    }


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_flujo_completo_reserva(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)

    # Disponibilidad antes de reservar
    params = {"sede_id": p["sede_id"], "tipo": "carro", "fecha_inicio": _iso(inicio), "fecha_fin": _iso(inicio + timedelta(hours=2))}
    assert len((await client.get(f"{API}/espacios/disponibles", params=params)).json()) == 1

    res = await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))
    assert res.status_code == 201, res.text
    reserva = res.json()
    assert reserva["estado"] == "pendiente"
    assert reserva["total"] == 9000  # 2 horas x 4500
    assert reserva["saldo"] == 9000

    # Ya no está disponible y no se puede reservar dos veces en el mismo horario
    assert (await client.get(f"{API}/espacios/disponibles", params=params)).json() == []
    res = await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio + timedelta(hours=1)))
    assert res.status_code == 409

    # Entrada: el espacio queda ocupado
    rid = reserva["id"]
    res = await client.post(f"{API}/reservas/{rid}/entrada", headers=p["admin"])
    assert res.status_code == 200, res.text
    assert res.json()["sesion"]["estado"] == "activa"
    assert (await client.get(f"{API}/espacios/{p['espacio_id']}")).json()["estado"] == "ocupado"

    # No se puede cancelar con el carro adentro
    assert (await client.post(f"{API}/reservas/{rid}/cancelar", headers=usuario)).status_code == 409

    # Salida: se cobra mínimo 1 hora y el espacio se libera
    res = await client.post(f"{API}/reservas/{rid}/salida", headers=p["admin"])
    assert res.status_code == 200, res.text
    reserva = res.json()
    assert reserva["estado"] == "completada"
    assert reserva["total"] == 4500
    assert (await client.get(f"{API}/espacios/{p['espacio_id']}")).json()["estado"] == "disponible"

    # Pagos
    res = await client.post(f"{API}/reservas/{rid}/pagos", headers=usuario, json={"monto": 5000, "metodo_pago": "app"})
    assert res.status_code == 422  # supera el saldo
    res = await client.post(f"{API}/reservas/{rid}/pagos", headers=usuario, json={"monto": 4500, "metodo_pago": "efectivo"})
    assert res.status_code == 403  # el usuario solo paga por la app
    res = await client.post(f"{API}/reservas/{rid}/pagos", headers=usuario, json={"monto": 4500, "metodo_pago": "app"})
    assert res.status_code == 201, res.text
    assert res.json()["saldo"] == 0
    assert res.json()["pagos"][0]["estado"] == "pagado"

    mias = (await client.get(f"{API}/reservas/mias", headers=usuario)).json()
    assert [r["id"] for r in mias] == [rid]


async def test_cancelar_libera_horario(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)

    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()["id"]
    res = await client.post(f"{API}/reservas/{rid}/cancelar", headers=usuario)
    assert res.json()["estado"] == "cancelada"
    assert res.json()["total"] == 0

    res = await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))
    assert res.status_code == 201


async def test_validaciones_reserva(client):
    p = await _setup_parqueadero(client)
    usuario, vehiculo_id = await _setup_usuario(client)
    otro, _ = await _setup_usuario(client, "otro@example.com")
    inicio = datetime.now(timezone.utc) + timedelta(hours=1)

    # Vehículo ajeno
    res = await client.post(f"{API}/reservas", headers=otro, json=_reserva_body(p, vehiculo_id, inicio))
    assert res.status_code == 422

    # Tarifa de moto en espacio de carro
    moto = await client.post(f"{API}/tarifas", headers=p["admin"], json={
        "sede_id": p["sede_id"], "nombre": "Moto", "tipo_vehiculo": "moto", "valor_hora": 2000,
    })
    body = _reserva_body(p, vehiculo_id, inicio)
    body["tarifa_id"] = moto.json()["id"]
    assert (await client.post(f"{API}/reservas", headers=usuario, json=body)).status_code == 422

    # Otro usuario no ve la reserva
    rid = (await client.post(f"{API}/reservas", headers=usuario, json=_reserva_body(p, vehiculo_id, inicio))).json()["id"]
    assert (await client.get(f"{API}/reservas/{rid}", headers=otro)).status_code == 404


async def test_permisos(client):
    p = await _setup_parqueadero(client)
    usuario, _ = await _setup_usuario(client)
    otro = await _setup_parqueadero(client, nit="900-2", admin_email="admin2@p.com")

    # Un usuario no puede crear espacios
    res = await client.post(f"{API}/espacios", headers=usuario, json={"sede_id": p["sede_id"], "codigo": "B-1", "tipo": "moto"})
    assert res.status_code == 403

    # El admin de otro parqueadero no puede tocar esta sede ni este parqueadero
    res = await client.post(f"{API}/espacios", headers=otro["admin"], json={"sede_id": p["sede_id"], "codigo": "B-1", "tipo": "moto"})
    assert res.status_code == 404
    res = await client.patch(f"{API}/parqueaderos/{p['parqueadero']['id']}", headers=otro["admin"], json={"nombre": "X"})
    assert res.status_code == 403

    # Un operador no puede crear empleados
    await client.post(f"{API}/empleados", headers=p["admin"], json={"nombre": "Op", "email": "op@p.com", "password": "secreto123"})
    operador = await _login(client, "empleados", "op@p.com")
    res = await client.post(f"{API}/empleados", headers=operador, json={"nombre": "X", "email": "x@p.com", "password": "secreto123"})
    assert res.status_code == 403

    # Sin token
    assert (await client.get(f"{API}/usuarios/me")).status_code == 401


async def test_listar_parqueaderos_por_ciudad(client):
    await _setup_parqueadero(client)
    assert len((await client.get(f"{API}/parqueaderos", params={"ciudad": "bogotá"})).json()) == 1
    assert (await client.get(f"{API}/parqueaderos", params={"ciudad": "Cali"})).json() == []


async def test_datos_duplicados(client):
    await _setup_parqueadero(client)
    res = await client.post(f"{API}/parqueaderos", json={
        "nombre": "Otro", "nit": "900-1", "email_contacto": "x@p.com",
        "administrador": {"nombre": "A", "email": "nuevo@p.com", "password": "secreto123"},
    })
    assert res.status_code == 409
    await _setup_usuario(client)
    res = await client.post(f"{API}/auth/usuarios/registro", json={"nombre": "C", "email": "CARLOS@example.com", "password": "secreto123"})
    assert res.status_code == 409
