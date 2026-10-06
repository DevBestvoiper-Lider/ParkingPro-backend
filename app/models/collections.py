"""Nombres, validadores ($jsonSchema) e índices de las colecciones de ParkingPro."""
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

PARQUEADEROS = "parqueaderos"
EMPLEADOS = "empleados"
USUARIOS = "usuarios"
ESPACIOS = "espacios_parqueo"
TARIFAS = "tarifas"
RESERVAS = "reservas"
CONTADORES = "contadores"  # secuencias para códigos legibles (Rsv-000123, TX-000045)
ACTIVIDAD = "actividad"
SUSCRIPCIONES = "suscripciones"
NOTIFICACIONES = "notificaciones"
ALERTAS_CUPO = "alertas_cupo"
INTERESADOS = "interesados"  # quién está viendo una sede/plaza (expira solo)

VALIDATORS = {
    PARQUEADEROS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "parqueaderos",
            "required": ["nombre", "nit", "email_contacto", "estado", "fecha_registro"],
            "properties": {
                "nombre": {"bsonType": "string"},
                "nit": {"bsonType": "string"},
                "email_contacto": {"bsonType": "string"},
                "telefono": {"bsonType": "string"},
                "estado": {"bsonType": "string", "enum": ["activo", "suspendido", "en_prueba"]},
                "fecha_registro": {"bsonType": "date"},
                "sedes": {
                    "bsonType": "array",
                    "items": {
                        "bsonType": "object",
                        "required": ["nombre", "direccion", "ciudad", "estado"],
                        "properties": {
                            "nombre": {"bsonType": "string"},
                            "direccion": {"bsonType": "string"},
                            "ciudad": {"bsonType": "string"},
                            "telefono": {"bsonType": "string"},
                            "estado": {"bsonType": "string", "enum": ["activa", "inactiva", "mantenimiento"]},
                            # agregado para el mapa: GeoJSON Point [longitud, latitud]
                            "ubicacion": {
                                "bsonType": "object",
                                "required": ["type", "coordinates"],
                                "properties": {
                                    "type": {"enum": ["Point"]},
                                    "coordinates": {
                                        "bsonType": "array",
                                        "minItems": 2,
                                        "maxItems": 2,
                                        "items": {"bsonType": "number"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    },
    EMPLEADOS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "empleados",
            "required": ["parqueadero_id", "nombre", "email", "rol", "estado"],
            "properties": {
                "parqueadero_id": {"bsonType": "objectId"},
                "nombre": {"bsonType": "string"},
                "email": {"bsonType": "string"},
                "rol": {"bsonType": "string", "enum": ["administrador", "operador", "cajero"]},
                "estado": {"bsonType": "string", "enum": ["activo", "inactivo"]},
                "password_hash": {"bsonType": "string"},  # agregado para el login
                "sesion_version": {"bsonType": "int"},  # sube al cambiar la clave; invalida el refresh
                "reset_token_hash": {"bsonType": "string"},
                "reset_expira": {"bsonType": "date"},
            },
        }
    },
    USUARIOS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "usuarios",
            "required": ["nombre", "email"],
            "properties": {
                "nombre": {"bsonType": "string"},
                "email": {"bsonType": "string"},
                "telefono": {"bsonType": "string"},
                "password_hash": {"bsonType": "string"},  # agregado para el login
                "sesion_version": {"bsonType": "int"},  # sube al cambiar la clave; invalida el refresh
                "reset_token_hash": {"bsonType": "string"},
                "reset_expira": {"bsonType": "date"},
                "vehiculos": {
                    "bsonType": "array",
                    "items": {
                        "bsonType": "object",
                        "required": ["placa"],
                        "properties": {
                            "placa": {"bsonType": "string"},
                            "marca": {"bsonType": "string"},
                            "modelo": {"bsonType": "string"},
                            "color": {"bsonType": "string"},
                        },
                    },
                },
            },
        }
    },
    ESPACIOS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "espacios_parqueo",
            "required": ["parqueadero_id", "sede_id", "codigo", "tipo", "estado"],
            "properties": {
                "parqueadero_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
                "codigo": {"bsonType": "string"},
                "zona": {"bsonType": "string"},
                "tipo": {"bsonType": "string", "enum": ["carro", "moto", "discapacitado"]},
                "estado": {"bsonType": "string", "enum": ["disponible", "ocupado", "mantenimiento"]},
            },
        }
    },
    TARIFAS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "tarifas",
            "required": ["parqueadero_id", "sede_id", "nombre", "tipo_vehiculo", "valor_hora"],
            "properties": {
                "parqueadero_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
                "nombre": {"bsonType": "string"},
                "tipo_vehiculo": {"bsonType": "string", "enum": ["carro", "moto"]},
                "valor_hora": {"bsonType": "decimal", "minimum": 0},
            },
        }
    },
    RESERVAS: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "reservas",
            "required": [
                "parqueadero_id", "sede_id", "usuario_id", "vehiculo_id",
                "espacio_id", "tarifa_id", "fecha_inicio", "fecha_fin", "estado",
            ],
            "properties": {
                "parqueadero_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
                "usuario_id": {"bsonType": "objectId"},
                "vehiculo_id": {"bsonType": "objectId"},
                "espacio_id": {"bsonType": "objectId"},
                "tarifa_id": {"bsonType": "objectId"},
                "codigo": {"bsonType": "string"},  # agregado: código legible, ej. Rsv-000123
                "fecha_inicio": {"bsonType": "date"},
                "fecha_fin": {"bsonType": "date"},
                "estado": {"bsonType": "string", "enum": ["pendiente", "confirmada", "cancelada", "completada"]},
                "tarifa_aplicada": {
                    "bsonType": "object",
                    "required": ["nombre", "valor_hora"],
                    "properties": {
                        "nombre": {"bsonType": "string"},
                        "valor_hora": {"bsonType": "decimal"},
                        "descuento_pct": {"bsonType": "int"},  # agregado: plan Afiliado
                    },
                },
                "sesion": {
                    "bsonType": "object",
                    "properties": {
                        "hora_entrada": {"bsonType": "date"},
                        "hora_salida": {"bsonType": "date"},
                        "estado": {"bsonType": "string", "enum": ["activa", "finalizada"]},
                    },
                },
                "pagos": {
                    "bsonType": "array",
                    "items": {
                        "bsonType": "object",
                        "required": ["monto", "fecha_pago", "metodo_pago", "estado"],
                        "properties": {
                            "codigo": {"bsonType": "string"},  # agregado: TX-000045
                            "monto": {"bsonType": "decimal", "minimum": 0},
                            "fecha_pago": {"bsonType": "date"},
                            "metodo_pago": {"bsonType": "string", "enum": ["efectivo", "tarjeta", "app"]},
                            "estado": {"bsonType": "string", "enum": ["pendiente", "pagado", "rechazado", "reembolsado"]},
                        },
                    },
                },
            },
        }
    },
}

# ---- Colecciones agregadas para el panel web, el plan Afiliado y las notificaciones ----
VALIDATORS.update({
    ACTIVIDAD: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "actividad",
            "required": ["parqueadero_id", "sede_id", "tipo", "descripcion", "fecha"],
            "properties": {
                "parqueadero_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
                "tipo": {"bsonType": "string", "enum": [
                    "reserva_creada", "reserva_confirmada", "reserva_cancelada", "reserva_vencida",
                    "check_in", "check_out", "pago", "reembolso", "espacio_estado",
                ]},
                "descripcion": {"bsonType": "string"},
                "reserva_id": {"bsonType": "objectId"},
                "espacio_id": {"bsonType": "objectId"},
                "fecha": {"bsonType": "date"},
            },
        }
    },
    SUSCRIPCIONES: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "suscripciones",
            "required": ["usuario_id", "plan", "precio", "fecha_inicio", "fecha_fin", "estado"],
            "properties": {
                "usuario_id": {"bsonType": "objectId"},
                "plan": {"bsonType": "string", "enum": ["afiliado"]},
                "precio": {"bsonType": "decimal", "minimum": 0},
                "descuento_pct": {"bsonType": "int"},
                "fecha_inicio": {"bsonType": "date"},
                "fecha_fin": {"bsonType": "date"},
                "estado": {"bsonType": "string", "enum": ["activa", "cancelada", "vencida"]},
                "renovacion_automatica": {"bsonType": "bool"},
                "metodo_pago": {"bsonType": "string", "enum": ["tarjeta", "app"]},
            },
        }
    },
    NOTIFICACIONES: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "notificaciones",
            "required": ["usuario_id", "titulo", "mensaje", "leida", "fecha"],
            "properties": {
                "usuario_id": {"bsonType": "objectId"},
                "titulo": {"bsonType": "string"},
                "mensaje": {"bsonType": "string"},
                "leida": {"bsonType": "bool"},
                "fecha": {"bsonType": "date"},
                "reserva_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
            },
        }
    },
    ALERTAS_CUPO: {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "alertas_cupo",
            "required": ["usuario_id", "sede_id", "fecha_creacion"],
            "properties": {
                "usuario_id": {"bsonType": "objectId"},
                "sede_id": {"bsonType": "objectId"},
                "tipo": {"bsonType": "string", "enum": ["carro", "moto", "discapacitado"]},
                "fecha_creacion": {"bsonType": "date"},
                "ultima_notificacion": {"bsonType": "date"},
            },
        }
    },
})

INDEXES = {
    PARQUEADEROS: [
        IndexModel([("nit", ASCENDING)], unique=True),
        IndexModel([("sedes._id", ASCENDING)]),
        IndexModel([("sedes.ciudad", ASCENDING)]),
    ],
    EMPLEADOS: [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("parqueadero_id", ASCENDING)]),
    ],
    USUARIOS: [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("vehiculos.placa", ASCENDING)]),
        IndexModel([("nombre", ASCENDING)]),
    ],
    ESPACIOS: [
        IndexModel([("sede_id", ASCENDING), ("codigo", ASCENDING)], unique=True),
        IndexModel([("sede_id", ASCENDING), ("tipo", ASCENDING), ("estado", ASCENDING)]),
    ],
    TARIFAS: [IndexModel([("sede_id", ASCENDING), ("tipo_vehiculo", ASCENDING)])],
    RESERVAS: [
        IndexModel([("codigo", ASCENDING)], unique=True),
        IndexModel([("parqueadero_id", ASCENDING), ("pagos.fecha_pago", DESCENDING)]),
        IndexModel([("estado", ASCENDING), ("_id", ASCENDING)]),  # vencer pendientes
        IndexModel([("vehiculo_id", ASCENDING), ("sesion.estado", ASCENDING)]),
        IndexModel([("espacio_id", ASCENDING), ("estado", ASCENDING), ("fecha_inicio", ASCENDING)]),
        IndexModel([("usuario_id", ASCENDING), ("fecha_inicio", DESCENDING)]),
        IndexModel([("parqueadero_id", ASCENDING), ("sede_id", ASCENDING), ("fecha_inicio", DESCENDING)]),
    ],
}

INDEXES.update({
    ACTIVIDAD: [
        IndexModel([("parqueadero_id", ASCENDING), ("fecha", DESCENDING)]),
        IndexModel([("fecha", ASCENDING)], expireAfterSeconds=90 * 24 * 3600),  # se guarda 90 días
    ],
    SUSCRIPCIONES: [IndexModel([("usuario_id", ASCENDING), ("estado", ASCENDING), ("fecha_fin", DESCENDING)])],
    NOTIFICACIONES: [IndexModel([("usuario_id", ASCENDING), ("leida", ASCENDING), ("fecha", DESCENDING)])],
    ALERTAS_CUPO: [
        IndexModel([("usuario_id", ASCENDING), ("sede_id", ASCENDING)], unique=True),
        IndexModel([("sede_id", ASCENDING)]),
    ],
    INTERESADOS: [
        IndexModel([("sede_id", ASCENDING), ("expira", ASCENDING)]),
        IndexModel([("expira", ASCENDING)], expireAfterSeconds=0),
    ],
})


async def apply_validators(db: AsyncDatabase) -> None:
    """Crea las colecciones con su validador, o lo actualiza si ya existen (requiere rol dbAdmin)."""
    existentes = set(await db.list_collection_names())
    for nombre, validator in VALIDATORS.items():
        if nombre in existentes:
            await db.command("collMod", nombre, validator=validator)
        else:
            await db.create_collection(nombre, validator=validator)


async def ensure_indexes(db: AsyncDatabase) -> None:
    for nombre, indexes in INDEXES.items():
        await db[nombre].create_indexes(indexes)
