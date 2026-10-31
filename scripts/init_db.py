"""Crea la base, las colecciones con sus validadores y los índices, y migra datos existentes.

Uso:
    python -m scripts.init_db           # colecciones + validadores + índices
    python -m scripts.init_db --seed    # además inserta los datos de ejemplo del modelo
    python -m scripts.init_db --demo    # además crea el demo de Cartagena para el frontend
"""
import argparse
import asyncio
from datetime import timedelta
from decimal import Decimal

from bson import ObjectId

from app.core.config import settings
from app.core.comision import condiciones_parqueadero, condiciones_socio
from app.core.database import close_client, get_db
from app.core.security import hash_password
from app.core.utils import as_utc, punto, to_decimal128, utcnow
from app.models import collections as c
from app.models.enums import PERMISOS
from app.repositories.contador_repository import ContadorRepository
from app.services.acceso import accesos
from scripts.demo_cartagena import crear_demo

UBICACION_CHAPINERO = punto(4.6486, -74.0628)
SOCIO_PRUEBA = "socio@demo.parkingpro.co"
ADMIN_CAMARA = "luisda3231@gmail.com"


async def migrar(db) -> None:
    """Completa campos agregados después de crear los datos: códigos de reserva."""
    contadores = ContadorRepository(db)
    sin_codigo = await db[c.RESERVAS].find({"codigo": {"$exists": False}}).sort("fecha_inicio", 1).to_list(None)
    for reserva in sin_codigo:
        codigo = f"Rsv-{await contadores.siguiente('reservas'):06d}"
        await db[c.RESERVAS].update_one({"_id": reserva["_id"]}, {"$set": {"codigo": codigo}})
    if sin_codigo:
        print(f"Códigos asignados a {len(sin_codigo)} reserva(s) existentes.")


async def migrar_socios(db) -> None:
    """Un socio de prueba queda dueño de los parqueaderos sin dueño; los empleados pasan a `accesos`.

    Los administradores existentes quedan con todos los permisos. El `parqueadero_id` viejo se conserva
    para que la API desplegada siga funcionando hasta actualizarla.
    """
    if await db[c.PARQUEADEROS].count_documents({"socio_id": {"$exists": False}}):
        socio = await db[c.SOCIOS].find_one({"email": SOCIO_PRUEBA})
        if not socio:
            socio = {
                "nombre": "Socio de prueba", "email": SOCIO_PRUEBA, "estado": "activo", "fecha_registro": utcnow(),
                "password_hash": hash_password(settings.SEED_PASSWORD), "sesion_version": 0,
            }
            socio["_id"] = (await db[c.SOCIOS].insert_one(socio)).inserted_id
        res = await db[c.PARQUEADEROS].update_many({"socio_id": {"$exists": False}}, {"$set": {"socio_id": socio["_id"]}})
        print(f"{res.modified_count} parqueadero(s) quedan del socio de prueba ({SOCIO_PRUEBA}).")

    sin_accesos = await db[c.EMPLEADOS].find({"accesos": {"$exists": False}}).to_list(None)
    for empleado in sin_accesos:
        await db[c.EMPLEADOS].update_one({"_id": empleado["_id"]}, {"$set": {"accesos": accesos(empleado)}})
    if sin_accesos:
        print(f"Accesos asignados a {len(sin_accesos)} empleado(s).")

    # Dinero: lo pactado se copia de la política actual. Los pagos anteriores a hoy no se liquidan.
    res = await db[c.SOCIOS].update_many(
        {"condiciones": {"$exists": False}},
        {"$set": {"condiciones": condiciones_socio(), "liquida_desde": utcnow()}},
    )
    if res.modified_count:
        print(f"Condiciones asignadas a {res.modified_count} socio(s).")
    sin_condiciones = await db[c.PARQUEADEROS].find({"condiciones": {"$exists": False}}).to_list(None)
    for parqueadero in sin_condiciones:
        condiciones = condiciones_parqueadero(as_utc(parqueadero.get("fecha_registro") or utcnow()))
        await db[c.PARQUEADEROS].update_one({"_id": parqueadero["_id"]}, {"$set": {"condiciones": condiciones}})
    if sin_condiciones:
        print(f"Condiciones de prueba asignadas a {len(sin_condiciones)} parqueadero(s).")


async def migrar_admin_camara(db) -> None:
    """El admin de la app también opera la cámara, sin una segunda cuenta de empleado.

    Si ya existe el empleado, no se toca su clave. Si no, se crea como administrador del
    primer parqueadero activo (la contraseña de empleado es SEED_PASSWORD; la de la app no cambia).
    """
    parqueadero = await db[c.PARQUEADEROS].find_one({"estado": "activo"}, sort=[("fecha_registro", 1)])
    if not parqueadero:
        return
    accesos_admin = [{"parqueadero_id": parqueadero["_id"], "permisos": sorted(PERMISOS)}]
    existente = await db[c.EMPLEADOS].find_one({"email": ADMIN_CAMARA})
    if existente:
        cambios = {}
        if existente.get("estado") != "activo":
            cambios["estado"] = "activo"
        if existente.get("rol") != "administrador":
            cambios["rol"] = "administrador"
        if "accesos" not in existente:
            cambios["accesos"] = accesos_admin
            cambios["parqueadero_id"] = parqueadero["_id"]
        if cambios:
            await db[c.EMPLEADOS].update_one({"_id": existente["_id"]}, {"$set": cambios})
            print(f"Admin de cámara actualizado ({ADMIN_CAMARA}).")
        return

    usuario = await db[c.USUARIOS].find_one({"email": ADMIN_CAMARA})
    await db[c.EMPLEADOS].insert_one({
        "parqueadero_id": parqueadero["_id"],
        "nombre": (usuario or {}).get("nombre") or "Luis Sandon",
        "email": ADMIN_CAMARA,
        "rol": "administrador",
        "estado": "activo",
        "password_hash": hash_password(settings.SEED_PASSWORD),
        "sesion_version": 0,
        "accesos": accesos_admin,
    })
    print(f"Admin de cámara creado ({ADMIN_CAMARA}) en {parqueadero['nombre']}.")


async def seed(db) -> None:
    existente = await db[c.PARQUEADEROS].find_one({"nit": "900123456-7"})
    if existente:
        # La sede de ejemplo se creó antes de existir el mapa: le ponemos ubicación.
        await db[c.PARQUEADEROS].update_one(
            {"_id": existente["_id"], "sedes": {"$elemMatch": {"nombre": "Sede Chapinero", "ubicacion": {"$exists": False}}}},
            {"$set": {"sedes.$.ubicacion": UBICACION_CHAPINERO}},
        )
        print("Los datos de ejemplo ya existen, no se insertan de nuevo.")
        return

    password_hash = hash_password(settings.SEED_PASSWORD)
    sede_id = ObjectId()
    parqueadero_id = (await db[c.PARQUEADEROS].insert_one({
        "nombre": "ParkingPro Centro",
        "nit": "900123456-7",
        "email_contacto": "contacto@parkingprocentro.com",
        "telefono": "3001234567",
        "estado": "activo",
        "fecha_registro": utcnow(),
        "sedes": [{
            "_id": sede_id,
            "nombre": "Sede Chapinero",
            "direccion": "Cra 13 # 45-67",
            "ciudad": "Bogotá",
            "telefono": "3011234567",
            "estado": "activa",
            "ubicacion": UBICACION_CHAPINERO,
        }],
    })).inserted_id

    await db[c.EMPLEADOS].insert_one({
        "parqueadero_id": parqueadero_id,
        "nombre": "Laura Gómez",
        "email": "laura.gomez@parkingprocentro.com",
        "rol": "administrador",
        "estado": "activo",
        "password_hash": password_hash,
    })

    vehiculo_id = ObjectId()
    usuario_id = (await db[c.USUARIOS].insert_one({
        "nombre": "Carlos Pérez",
        "email": "carlos.perez@example.com",
        "telefono": "3157654321",
        "password_hash": password_hash,
        "vehiculos": [{"_id": vehiculo_id, "placa": "ABC123", "marca": "Mazda", "modelo": "3", "color": "Rojo"}],
    })).inserted_id

    espacio_id = (await db[c.ESPACIOS].insert_one({
        "parqueadero_id": parqueadero_id,
        "sede_id": sede_id,
        "codigo": "A-12",
        "zona": "Sótano 1",
        "tipo": "carro",
        "estado": "disponible",
    })).inserted_id

    valor_hora = to_decimal128(Decimal("4500"))
    tarifa_id = (await db[c.TARIFAS].insert_one({
        "parqueadero_id": parqueadero_id,
        "sede_id": sede_id,
        "nombre": "Tarifa carro diurna",
        "tipo_vehiculo": "carro",
        "valor_hora": valor_hora,
    })).inserted_id

    entrada = utcnow() - timedelta(hours=3)
    salida = entrada + timedelta(hours=2)
    await db[c.RESERVAS].insert_one({
        "parqueadero_id": parqueadero_id,
        "sede_id": sede_id,
        "usuario_id": usuario_id,
        "vehiculo_id": vehiculo_id,
        "espacio_id": espacio_id,
        "tarifa_id": tarifa_id,
        "codigo": f"Rsv-{await ContadorRepository(db).siguiente('reservas'):06d}",
        "fecha_inicio": entrada,
        "fecha_fin": salida,
        "estado": "completada",
        "tarifa_aplicada": {"nombre": "Tarifa carro diurna", "valor_hora": valor_hora},
        "sesion": {"hora_entrada": entrada, "hora_salida": salida, "estado": "finalizada"},
        "pagos": [{
            "_id": ObjectId(),
            "monto": to_decimal128(Decimal("9000")),
            "fecha_pago": salida,
            "metodo_pago": "tarjeta",
            "estado": "pagado",
        }],
    })
    print("Datos de ejemplo insertados (contraseña: SEED_PASSWORD del .env).")


async def main(with_seed: bool, with_demo: bool) -> None:
    db = get_db()
    try:
        await db.command("ping")
        print(f"Conectado a MongoDB, base '{settings.MONGODB_DB}'.")
        await c.apply_validators(db)
        print("Colecciones creadas/actualizadas con sus validadores.")
        await migrar(db)  # antes de los índices: el código de reserva es único
        await c.ensure_indexes(db)
        print("Índices creados.")
        if with_seed:
            await seed(db)
        if with_demo:
            await crear_demo(db)
        await migrar_socios(db)  # también para los datos de ejemplo recién creados
        await migrar_admin_camara(db)
    finally:
        await close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="Inserta los datos de ejemplo")
    parser.add_argument("--demo", action="store_true", help="Crea el demo de Cartagena")
    args = parser.parse_args()
    asyncio.run(main(args.seed, args.demo))
