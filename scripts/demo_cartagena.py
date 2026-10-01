"""Datos de demostración en Cartagena para desarrollar y presentar el frontend.

Crea 2 parqueaderos, 4 sedes con coordenadas reales, zonas A-D con plazas, tarifas,
empleados, clientes (uno Afiliado) y una semana de reservas con pagos. Es idempotente:
si el parqueadero demo ya existe no hace nada.
"""
import random
from datetime import timedelta
from decimal import Decimal

from bson import ObjectId

from app.core.billing import calcular_total
from app.core.config import settings
from app.core.security import hash_password
from app.core.utils import punto, to_decimal128, utcnow
from app.models import collections as c
from app.repositories.contador_repository import ContadorRepository

NIT_DEMO = "900555001-1"
DOMINIO = "demo.parkingpro.co"

PARQUEADEROS = [
    {
        "nombre": "ParkingPro Cartagena",
        "nit": NIT_DEMO,
        "email_contacto": f"contacto@{DOMINIO}",
        "telefono": "6056641234",
        "sedes": [
            ("Sede Centro Histórico", "Cl. 35 #3-20, Centro", 10.4236, -75.5510, {"carro": 4500, "moto": 2000}),
            ("Sede Bocagrande", "Av. San Martín #6-50, Bocagrande", 10.3997, -75.5553, {"carro": 6000, "moto": 2500}),
            ("Sede Manga", "Cl. 25 #20-45, Manga", 10.4131, -75.5367, {"carro": 3500, "moto": 1500}),
        ],
    },
    {
        "nombre": "Parqueaderos Getsemaní",
        "nit": "900555002-9",
        "email_contacto": f"getsemani@{DOMINIO}",
        "telefono": "6056645678",
        "sedes": [
            ("Sede Getsemaní", "Cl. del Arsenal #10-15, Getsemaní", 10.4219, -75.5476, {"carro": 5000, "moto": 2000}),
        ],
    },
]

# zona -> (cantidad, tipo); la Zona B incluye 2 plazas para discapacitados
ZONAS = {"Zona A": (20, "carro"), "Zona B": (20, "carro"), "Zona C": (10, "moto"), "Zona D": (10, "carro")}

CLIENTES = [
    ("Carlos Pérez", "ABC123", "Mazda", "3", "Rojo"),
    ("María Gómez", "XYZ789", "Renault", "Sandero", "Gris"),
    ("Andrés Ruiz", "NOP456", "Chevrolet", "Onix", "Blanco"),
    ("Laura Díaz", "QRS123", "Kia", "Picanto", "Azul"),
    ("Julián Torres", "TUV98F", "Yamaha", "NMAX", "Negro"),  # moto
    ("Sofía Martín", "DEF456", "Toyota", "Corolla", "Plata"),
]


async def crear_demo(db) -> bool:
    if await db[c.PARQUEADEROS].find_one({"nit": NIT_DEMO}):
        print("El demo de Cartagena ya existe, no se crea de nuevo.")
        return False

    rnd = random.Random(42)
    contadores = ContadorRepository(db)
    password = hash_password(settings.SEED_PASSWORD)
    ahora = utcnow()

    # ---------- Parqueaderos, sedes, espacios, tarifas, empleados ----------
    sedes_info = []  # (parqueadero_id, sede_id, espacios, tarifas)
    for i, datos in enumerate(PARQUEADEROS):
        sedes = []
        for nombre, direccion, lat, lng, _ in datos["sedes"]:
            sedes.append({"_id": ObjectId(), "nombre": nombre, "direccion": direccion, "ciudad": "Cartagena",
                          "telefono": datos["telefono"], "estado": "activa", "ubicacion": punto(lat, lng)})
        pid = (await db[c.PARQUEADEROS].insert_one({
            "nombre": datos["nombre"], "nit": datos["nit"], "email_contacto": datos["email_contacto"],
            "telefono": datos["telefono"], "estado": "activo", "fecha_registro": ahora - timedelta(days=60),
            "sedes": sedes,
        })).inserted_id

        prefijo = "admin" if i == 0 else "admin.getsemani"
        empleados = [(f"{prefijo}@{DOMINIO}", "Juan Administrador", "administrador")]
        if i == 0:
            empleados += [(f"operador@{DOMINIO}", "Ana Operadora", "operador"), (f"cajero@{DOMINIO}", "Luis Cajero", "cajero")]
        await db[c.EMPLEADOS].insert_many([
            {"parqueadero_id": pid, "nombre": n, "email": e, "rol": r, "estado": "activo", "password_hash": password}
            for e, n, r in empleados
        ])

        for sede, (_, _, _, _, precios) in zip(sedes, datos["sedes"]):
            espacios = []
            for zona, (cantidad, tipo) in ZONAS.items():
                letra = zona[-1]
                for n in range(1, cantidad + 1):
                    tipo_plaza = "discapacitado" if zona == "Zona B" and n <= 2 else tipo
                    espacios.append({"_id": ObjectId(), "parqueadero_id": pid, "sede_id": sede["_id"],
                                     "codigo": f"{letra}-{n:02d}", "zona": zona, "tipo": tipo_plaza, "estado": "disponible"})
            espacios[26]["estado"] = "mantenimiento"  # Zona B - Plaza 07, como en el mockup
            await db[c.ESPACIOS].insert_many(espacios)
            tarifas = [
                {"_id": ObjectId(), "parqueadero_id": pid, "sede_id": sede["_id"], "nombre": f"Tarifa {tipo} diurna",
                 "tipo_vehiculo": tipo, "valor_hora": to_decimal128(Decimal(valor))}
                for tipo, valor in precios.items()
            ]
            await db[c.TARIFAS].insert_many(tarifas)
            sedes_info.append((pid, sede["_id"], espacios, {t["tipo_vehiculo"]: t for t in tarifas}))

    # ---------- Clientes ----------
    clientes = []
    for nombre, placa, marca, modelo, color in CLIENTES:
        vehiculo = {"_id": ObjectId(), "placa": placa, "marca": marca, "modelo": modelo, "color": color}
        email = nombre.lower().replace(" ", ".").replace("á", "a").replace("é", "e").replace("í", "i") + f"@{DOMINIO}"
        uid = (await db[c.USUARIOS].insert_one({
            "nombre": nombre, "email": email, "telefono": f"300{rnd.randint(1000000, 9999999)}",
            "password_hash": password, "vehiculos": [vehiculo],
        })).inserted_id
        clientes.append((uid, vehiculo, "moto" if placa.endswith("F") else "carro"))

    # Carlos es Afiliado
    await db[c.SUSCRIPCIONES].insert_one({
        "usuario_id": clientes[0][0], "plan": "afiliado", "precio": to_decimal128(Decimal(settings.AFILIADO_PRECIO_MENSUAL)),
        "descuento_pct": settings.AFILIADO_DESCUENTO_PCT, "fecha_inicio": ahora - timedelta(days=10),
        "fecha_fin": ahora + timedelta(days=20), "estado": "activa", "renovacion_automatica": True, "metodo_pago": "app",
    })

    # ---------- Reservas: 7 días de historial, sesiones activas y próximas ----------
    async def reserva(pid, sede_id, espacio, tarifa, cliente, inicio, horas, estado, sesion=None, pagos=()):
        uid, vehiculo, _ = cliente
        valor = tarifa["valor_hora"]
        aplicada = {"nombre": tarifa["nombre"], "valor_hora": valor}
        if uid == clientes[0][0]:
            descuento = settings.AFILIADO_DESCUENTO_PCT
            valor = to_decimal128(valor.to_decimal() * Decimal(100 - descuento) / 100)
            aplicada = {"nombre": f"{tarifa['nombre']} (Afiliado -{descuento}%)", "valor_hora": valor, "descuento_pct": descuento}
        doc = {
            "parqueadero_id": pid, "sede_id": sede_id, "usuario_id": uid, "vehiculo_id": vehiculo["_id"],
            "espacio_id": espacio["_id"], "tarifa_id": tarifa["_id"],
            "codigo": f"Rsv-{await contadores.siguiente('reservas'):06d}",
            "fecha_inicio": inicio, "fecha_fin": inicio + timedelta(hours=horas), "estado": estado,
            "tarifa_aplicada": aplicada, "pagos": [],
        }
        if sesion:
            doc["sesion"] = sesion
        for monto, metodo, fecha in pagos:
            doc["pagos"].append({
                "_id": ObjectId(), "codigo": f"TX-{await contadores.siguiente('pagos'):06d}",
                "monto": to_decimal128(monto), "fecha_pago": fecha, "metodo_pago": metodo, "estado": "pagado",
            })
        await db[c.RESERVAS].insert_one(doc)
        return doc

    principal = [s for s in sedes_info if s[0] == sedes_info[0][0]]
    total_reservas = 0
    for dias_atras in range(7, 0, -1):
        for _ in range(rnd.randint(5, 9)):
            pid, sede_id, espacios, tarifas = rnd.choice(principal)
            cliente = rnd.choice(clientes)
            tipo = cliente[2]
            espacio = rnd.choice([e for e in espacios if e["tipo"] == tipo and e["estado"] == "disponible"])
            inicio = (ahora - timedelta(days=dias_atras)).replace(hour=rnd.randint(12, 23), minute=rnd.choice([0, 15, 30, 45]))
            horas = rnd.randint(1, 4)
            if rnd.random() < 0.12:
                await reserva(pid, sede_id, espacio, tarifas[tipo], cliente, inicio, horas, "cancelada")
            else:
                salida = inicio + timedelta(hours=horas, minutes=-rnd.randint(0, 40))
                valor = tarifas[tipo]["valor_hora"].to_decimal()
                if cliente is clientes[0]:
                    valor = valor * Decimal(100 - settings.AFILIADO_DESCUENTO_PCT) / 100
                monto = calcular_total(valor, inicio, salida)
                metodo = rnd.choices(["tarjeta", "app", "efectivo"], weights=[52, 33, 15])[0]
                await reserva(pid, sede_id, espacio, tarifas[tipo], cliente, inicio, horas, "completada",
                              sesion={"hora_entrada": inicio, "hora_salida": salida, "estado": "finalizada"},
                              pagos=[(monto, metodo, salida)])
            total_reservas += 1

    # Ahora: 2 carros adentro en el Centro, y 3 reservas próximas
    pid, sede_id, espacios, tarifas = principal[0]
    libres = [e for e in espacios if e["tipo"] == "carro" and e["estado"] == "disponible"]
    for cliente, espacio, minutos in ((clientes[0], libres[11], 155), (clientes[5], libres[3], 40)):
        entrada = ahora - timedelta(minutes=minutos)
        await reserva(pid, sede_id, espacio, tarifas["carro"], cliente, entrada, 4, "confirmada",
                      sesion={"hora_entrada": entrada, "estado": "activa"})
        await db[c.ESPACIOS].update_one({"_id": espacio["_id"]}, {"$set": {"estado": "ocupado"}})
    for cliente, espacio, horas_despues, estado in ((clientes[1], libres[14], 2, "confirmada"),
                                                     (clientes[2], libres[25], 3, "pendiente"),
                                                     (clientes[3], libres[19], 24, "confirmada")):
        await reserva(pid, sede_id, espacio, tarifas["carro"], cliente, ahora + timedelta(hours=horas_despues), 2, estado)
    total_reservas += 5

    print(f"Demo de Cartagena creado: {len(sedes_info)} sedes, {sum(n for n, _ in ZONAS.values())} plazas por sede, "
          f"{len(clientes)} clientes, {total_reservas} reservas.")
    print(f"  Panel web: admin@{DOMINIO} · App: carlos.perez@{DOMINIO} (Afiliado) · contraseña: SEED_PASSWORD")
    return True
