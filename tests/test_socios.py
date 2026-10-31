import pytest
from bson import ObjectId

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import PERMISOS
from tests.test_parkingpro import API, _login, _setup_parqueadero

pytestmark = pytest.mark.asyncio


async def _socio_con_dos_parqueaderos(client):
    p = await _setup_parqueadero(client)
    socio = await _login(client, "socios", "socio.admin@p.com")
    res = await client.post(f"{API}/socios/me/parqueaderos", headers=socio, json={
        "nombre": "ParkingPro Manga", "nit": "900-77", "email_contacto": "manga@p.com",
    })
    assert res.status_code == 201, res.text
    assert res.json()["estado"] == "en_prueba"
    return p, socio, p["parqueadero"]["id"], res.json()["id"]


def _en(headers, parqueadero_id):
    return {**headers, "X-Parqueadero-Id": parqueadero_id}


async def test_socio_y_su_portafolio(client):
    p, socio, a, b = await _socio_con_dos_parqueaderos(client)

    me = (await client.get(f"{API}/socios/me", headers=socio)).json()
    assert me["email"] == "socio.admin@p.com" and me["estado"] == "activo"
    portafolio = (await client.get(f"{API}/socios/me/parqueaderos", headers=socio)).json()
    assert {x["id"] for x in portafolio} == {a, b}

    # Con dos parqueaderos tiene que elegir; el socio siempre tiene todos los permisos.
    res = await client.get(f"{API}/admin/dashboard", headers=socio)
    assert res.status_code == 400 and "X-Parqueadero-Id" in res.json()["detail"]
    assert (await client.get(f"{API}/admin/reportes", headers=_en(socio, a))).status_code == 200
    res = await client.post(f"{API}/parqueaderos/{b}/sedes", headers=_en(socio, b), json={
        "nombre": "Sede Manga", "direccion": "Cl. 25", "ciudad": "Cartagena",
    })
    assert res.status_code == 201, res.text

    # Un parqueadero que no es suyo
    otro = await _setup_parqueadero(client, nit="900-2", admin_email="admin2@p.com")
    res = await client.get(f"{API}/admin/dashboard", headers=_en(socio, otro["parqueadero"]["id"]))
    assert res.status_code == 403

    # La sesión del socio se renueva como las demás
    res = await client.post(f"{API}/auth/socios/login", data={"username": "socio.admin@p.com", "password": "secreto123"})
    res = await client.post(f"{API}/auth/refresh", json={"refresh_token": res.json()["refresh_token"]})
    assert res.status_code == 200 and res.json()["tipo"] == "socio"


async def test_cuentas_separadas(client):
    await _setup_parqueadero(client)
    # El socio no entra por el login de empleados ni puede registrarse como usuario con su email
    res = await client.post(f"{API}/auth/empleados/login", data={"username": "socio.admin@p.com", "password": "secreto123"})
    assert res.status_code == 401
    res = await client.post(f"{API}/auth/usuarios/registro", json={
        "nombre": "S", "email": "socio.admin@p.com", "password": "secreto123",
    })
    assert res.status_code == 409
    res = await client.post(f"{API}/parqueaderos", json={
        "nombre": "X", "nit": "900-3", "email_contacto": "x@p.com",
        "socio": {"nombre": "S", "email": "admin@p.com", "password": "secreto123"},
    })
    assert res.status_code == 409  # ya es el email de un empleado


async def test_permisos_del_administrador(client):
    p, socio, a, _ = await _socio_con_dos_parqueaderos(client)
    socio_a = _en(socio, a)

    res = await client.post(f"{API}/empleados", headers=socio_a, json={
        "nombre": "Admin sin permisos", "email": "vacio@p.com", "password": "secreto123", "rol": "administrador",
    })
    assert res.status_code == 422
    res = await client.post(f"{API}/empleados", headers=socio_a, json={
        "nombre": "Op", "email": "op@p.com", "password": "secreto123", "permisos": ["ver_operacion"],
    })
    assert res.status_code == 422  # operador y cajero tienen permisos fijos

    res = await client.post(f"{API}/empleados", headers=socio_a, json={
        "nombre": "Jefe de turno", "email": "turno@p.com", "password": "secreto123", "rol": "administrador",
        "permisos": ["ver_operacion", "gestionar_empleados"],
    })
    assert res.status_code == 201, res.text
    assert res.json()["accesos"] == [{"parqueadero_id": a, "permisos": ["gestionar_empleados", "ver_operacion"]}]
    turno = await _login(client, "empleados", "turno@p.com")

    assert (await client.get(f"{API}/admin/dashboard", headers=turno)).status_code == 200
    res = await client.post(f"{API}/tarifas", headers=turno, json={
        "sede_id": p["sede_id"], "nombre": "X", "tipo_vehiculo": "moto", "valor_hora": 1000,
    })
    assert res.status_code == 403 and "gestionar_tarifas" in res.json()["detail"]
    assert (await client.get(f"{API}/admin/reportes", headers=turno)).status_code == 403

    # Solo da lo que tiene
    res = await client.post(f"{API}/empleados", headers=turno, json={
        "nombre": "Otro", "email": "otro@p.com", "password": "secreto123", "rol": "administrador",
        "permisos": ["gestionar_tarifas"],
    })
    assert res.status_code == 403
    res = await client.post(f"{API}/empleados", headers=turno, json={
        "nombre": "Ayudante", "email": "ayudante@p.com", "password": "secreto123", "rol": "administrador",
        "permisos": ["ver_operacion"],
    })
    assert res.status_code == 201, res.text
    ayudante_id = res.json()["id"]

    # Un operador necesita cobrar en caja y ver métricas: el jefe de turno no los tiene
    res = await client.post(f"{API}/empleados", headers=turno, json={"nombre": "Op", "email": "op@p.com", "password": "secreto123"})
    assert res.status_code == 403

    # No toca a quien tiene más permisos que él, ni sus propios permisos
    empleados = (await client.get(f"{API}/empleados", headers=turno)).json()
    laura = next(e for e in empleados if e["email"] == "admin@p.com")
    res = await client.patch(f"{API}/empleados/{laura['id']}", headers=turno, json={"estado": "inactivo"})
    assert res.status_code == 403
    yo = next(e for e in empleados if e["email"] == "turno@p.com")
    res = await client.patch(f"{API}/empleados/{yo['id']}", headers=turno, json={"permisos": ["ver_operacion"]})
    assert res.status_code == 409

    # Al ayudante le puede quitar y poner lo que él tiene
    res = await client.patch(f"{API}/empleados/{ayudante_id}", headers=turno, json={
        "permisos": ["gestionar_empleados", "ver_operacion"],
    })
    assert res.status_code == 200, res.text
    res = await client.patch(f"{API}/empleados/{ayudante_id}", headers=turno, json={"permisos": ["ver_metricas"]})
    assert res.status_code == 403


async def test_administrador_en_dos_parqueaderos(client, db):
    p, socio, a, b = await _socio_con_dos_parqueaderos(client)
    res = await client.post(f"{API}/empleados", headers=_en(socio, a), json={
        "nombre": "Marta", "email": "marta@p.com", "password": "secreto123", "rol": "administrador",
        "permisos": ["gestionar_tarifas"],
    })
    assert res.status_code == 201, res.text
    res = await client.post(f"{API}/empleados/accesos", headers=_en(socio, b), json={
        "email": "marta@p.com", "permisos": ["ver_metricas"],
    })
    assert res.status_code == 200, res.text
    assert len(res.json()["accesos"]) == 2

    # Un administrador de otro socio no puede sumarla
    otro = await _setup_parqueadero(client, nit="900-2", admin_email="admin2@p.com")
    res = await client.post(f"{API}/empleados/accesos", headers=otro["admin"], json={
        "email": "marta@p.com", "permisos": ["ver_operacion"],
    })
    assert res.status_code == 404

    marta = await _login(client, "empleados", "marta@p.com")
    me = (await client.get(f"{API}/empleados/me", headers=marta)).json()
    assert {x["parqueadero_id"]: x["permisos"] for x in me["accesos"]} == {
        a: ["gestionar_tarifas"], b: ["ver_metricas"],
    }

    # Con un permiso en A y otro en B ve solo eso
    assert (await client.get(f"{API}/admin/reportes", headers=marta)).status_code == 400
    tarifa = {"sede_id": p["sede_id"], "nombre": "Moto", "tipo_vehiculo": "moto", "valor_hora": 2000}
    assert (await client.post(f"{API}/tarifas", headers=_en(marta, a), json=tarifa)).status_code == 201
    assert (await client.get(f"{API}/admin/reportes", headers=_en(marta, a))).status_code == 403
    assert (await client.get(f"{API}/admin/reportes", headers=_en(marta, b))).status_code == 200
    assert (await client.post(f"{API}/tarifas", headers=_en(marta, b), json=tarifa)).status_code == 403

    # Desde A no se le cambia la cuenta: también trabaja en B
    res = await client.patch(f"{API}/empleados/{me['id']}", headers=p["admin"], json={"nombre": "Marta R."})
    assert res.status_code == 409
    res = await client.delete(f"{API}/empleados/{me['id']}/acceso", headers=_en(socio, b))
    assert res.status_code == 204
    res = await client.delete(f"{API}/empleados/{me['id']}/acceso", headers=_en(socio, a))
    assert res.status_code == 409  # es su único parqueadero

    # Todo queda en el historial permanente, sin la clave
    acciones = [
        (x["accion"], x["entidad"], x["actor"]["tipo"])
        async for x in db["auditoria"].find({"entidad_id": ObjectId(me["id"])}).sort("fecha", 1)
    ]
    assert acciones == [
        ("crear", "empleado", "socio"), ("dar_acceso", "empleado", "socio"), ("quitar_acceso", "empleado", "socio"),
    ]
    creada = await db["auditoria"].find_one({"entidad": "tarifa", "despues.nombre": "Moto"})
    assert creada["actor"] == {"tipo": "empleado", "id": ObjectId(me["id"]), "nombre": "Marta"}
    assert creada["parqueadero_id"] == ObjectId(a) and creada["despues"]["valor_hora"].to_decimal() == 2000
    assert not await db["auditoria"].find_one({"despues.password_hash": {"$exists": True}})


async def test_migracion_al_socio_de_prueba(client, db):
    from scripts.demo_cartagena import crear_demo
    from scripts.init_db import SOCIO_PRUEBA, migrar_socios

    await crear_demo(db)  # datos de antes de los socios: sin dueño y con parqueadero_id
    await migrar_socios(db)
    await migrar_socios(db)  # se puede correr de nuevo

    socios = await db["socios"].find({}).to_list(None)
    assert [s["email"] for s in socios] == [SOCIO_PRUEBA]
    assert socios[0]["condiciones"]["comision_pct"] == 10 and "liquida_desde" in socios[0]
    assert await db["parqueaderos"].count_documents({"socio_id": socios[0]["_id"]}) == 2
    assert not await db["parqueaderos"].count_documents({"condiciones": {"$exists": False}})
    admin = await db["empleados"].find_one({"email": "admin@demo.parkingpro.co"})
    assert admin["accesos"] == [{"parqueadero_id": admin["parqueadero_id"], "permisos": sorted(PERMISOS)}]
    operador = await db["empleados"].find_one({"email": "operador@demo.parkingpro.co"})
    assert operador["accesos"][0]["permisos"] == []

    socio = await _login(client, "socios", SOCIO_PRUEBA, password=settings.SEED_PASSWORD)
    assert len((await client.get(f"{API}/socios/me/parqueaderos", headers=socio)).json()) == 2
    res = await client.get(f"{API}/admin/dashboard", headers=_en(socio, str(admin["parqueadero_id"])))
    assert res.status_code == 200, res.text


async def test_empleado_sin_migrar_sigue_entrando(client, db):
    p = await _setup_parqueadero(client)
    # Así quedaron los empleados antes de los socios: un parqueadero y un rol, sin accesos.
    await db["empleados"].insert_one({
        "parqueadero_id": ObjectId(p["parqueadero"]["id"]), "nombre": "Viejo", "email": "viejo@p.com",
        "rol": "administrador", "estado": "activo", "password_hash": hash_password("secreto123"),
    })
    viejo = await _login(client, "empleados", "viejo@p.com")
    me = (await client.get(f"{API}/empleados/me", headers=viejo)).json()
    assert me["accesos"][0]["parqueadero_id"] == p["parqueadero"]["id"]
    assert "gestionar_empleados" in me["accesos"][0]["permisos"]
    assert (await client.get(f"{API}/admin/reportes", headers=viejo)).status_code == 200
    emails = {e["email"] for e in (await client.get(f"{API}/empleados", headers=p["admin"])).json()}
    assert {"admin@p.com", "viejo@p.com"} <= emails
