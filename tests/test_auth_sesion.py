from datetime import datetime, timezone

import pytest

from tests.test_parkingpro import API, _setup_parqueadero, _setup_usuario

pytestmark = pytest.mark.asyncio


def _capturar(monkeypatch):
    enviados = []

    async def captura(email, nombre, token):
        enviados.append({"email": email, "nombre": nombre, "token": token})

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", captura)
    return enviados


async def _login(client, email, password="secreto123", tipo="usuarios"):
    res = await client.post(f"{API}/auth/{tipo}/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


async def test_refresh_renueva_la_sesion_y_no_sirve_como_access(client):
    await _setup_usuario(client)
    tokens = await _login(client, "carlos@example.com")
    assert tokens["tipo"] == "usuario"
    assert tokens["refresh_token"]

    renovado = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert renovado.status_code == 200, renovado.text
    nuevo = renovado.json()["access_token"]
    yo = await client.get(f"{API}/usuarios/me", headers={"Authorization": f"Bearer {nuevo}"})
    assert yo.status_code == 200
    assert yo.json()["email"] == "carlos@example.com"

    como_access = await client.get(
        f"{API}/usuarios/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert como_access.status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]})).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": "no-es-un-jwt"})).status_code == 401


async def test_recuperar_y_restablecer_invalida_la_sesion(client, monkeypatch):
    await _setup_usuario(client, "maria@example.com")
    tokens = await _login(client, "maria@example.com")
    enviados = _capturar(monkeypatch)

    ajeno = await client.post(f"{API}/auth/recuperar", json={"email": "nadie@example.com"})
    assert ajeno.status_code == 200
    assert ajeno.json()["mensaje"].startswith("Si el correo está registrado")
    assert enviados == []

    ok = await client.post(f"{API}/auth/recuperar", json={"email": "Maria@example.com"})
    assert ok.json()["mensaje"] == ajeno.json()["mensaje"]
    assert enviados[0]["email"] == "maria@example.com"
    token = enviados[0]["token"]

    otra = await client.post(f"{API}/auth/recuperar", json={"email": "maria@example.com"})
    assert otra.status_code == 200
    assert (await client.post(f"{API}/auth/restablecer", json={"token": token, "password": "nuevaclave1"})).status_code == 400

    vigente = enviados[-1]["token"]
    res = await client.post(f"{API}/auth/restablecer", json={"token": vigente, "password": "nuevaclave1"})
    assert res.status_code == 204
    assert (await client.post(f"{API}/auth/restablecer", json={"token": vigente, "password": "nuevaclave1"})).status_code == 400

    vieja = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get(f"{API}/usuarios/me", headers=vieja)).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    assert (await client.post(
        f"{API}/auth/usuarios/login", data={"username": "maria@example.com", "password": "secreto123"}
    )).status_code == 401
    nueva = await _login(client, "maria@example.com", password="nuevaclave1")
    assert (await client.get(
        f"{API}/usuarios/me", headers={"Authorization": f"Bearer {nueva['access_token']}"}
    )).status_code == 200


async def test_enlace_vencido_no_cambia_la_clave(client, db, monkeypatch):
    await _setup_usuario(client)
    enviados = _capturar(monkeypatch)
    await client.post(f"{API}/auth/recuperar", json={"email": "carlos@example.com"})
    await db.usuarios.update_one(
        {"email": "carlos@example.com"},
        {"$set": {"reset_expira": datetime(2020, 1, 1, tzinfo=timezone.utc)}},
    )
    res = await client.post(
        f"{API}/auth/restablecer", json={"token": enviados[0]["token"], "password": "nuevaclave1"}
    )
    assert res.status_code == 400


async def test_empleado_tambien_renueva_y_recupera(client, monkeypatch):
    await _setup_parqueadero(client)
    tokens = await _login(client, "admin@p.com", tipo="empleados")
    assert tokens["tipo"] == "empleado"
    renovado = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert renovado.status_code == 200
    assert renovado.json()["tipo"] == "empleado"

    enviados = _capturar(monkeypatch)
    await client.post(f"{API}/auth/recuperar", json={"email": "admin@p.com"})
    res = await client.post(
        f"{API}/auth/restablecer", json={"token": enviados[0]["token"], "password": "otraclave1"}
    )
    assert res.status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    await _login(client, "admin@p.com", password="otraclave1", tipo="empleados")
