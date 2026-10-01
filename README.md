# ParkingPro API

Backend de ParkingPro (app móvil + panel web de parqueaderos), hecho con FastAPI y MongoDB Atlas.
Arquitectura por capas: **Routers → Services → Repositories → MongoDB**.

```
app/
├── main.py            # App + "API Gateway" (/api/v1), CORS, lifespan (índices, Redis, tareas)
├── dependencies.py    # Inyección de dependencias (DB, repos, services, auth y roles)
├── core/              # config, database, security, billing, utils (zona horaria), realtime (WebSocket + Redis)
├── models/            # Colecciones: validadores $jsonSchema, índices y enums
├── schemas/           # Modelos Pydantic (request/response)
├── repositories/      # Acceso a datos por colección
├── services/          # Reglas de negocio
├── routers/           # Endpoints por módulo
└── tasks/             # Emails (background) y tareas periódicas (vencimientos)
scripts/init_db.py     # Colecciones + validadores + índices (+ --seed / --demo)
tests/                 # 30 tests con MongoDB en memoria
```

## Arranque

1. En Atlas: *Database > Connect > Drivers*, copia la URI y agrega tu IP en *Network Access*.
2. Crea `.env` a partir de `.env.example` y pega la URI en `MONGODB_URI`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.init_db --demo        # base + datos demo de Cartagena
uvicorn app.main:app --reload --host 0.0.0.0
```

Swagger: http://localhost:8000/docs · Desde el emulador Android: `http://10.0.2.2:8000`.

Con Docker: `docker build -t parkingpro-api . && docker run --env-file .env -p 8000:8000 parkingpro-api`

### Usuarios demo (contraseña = `SEED_PASSWORD`)

| Rol | Email |
|---|---|
| Administrador (panel web) | `admin@demo.parkingpro.co` |
| Operador / Cajero | `operador@demo.parkingpro.co` · `cajero@demo.parkingpro.co` |
| Usuario app, plan Afiliado, con sesión activa | `carlos.perez@demo.parkingpro.co` |
| Usuario app, plan por uso | `maria.gomez@demo.parkingpro.co` |

## Roles

| Quién | Puede |
|---|---|
| Invitado | Ver mapa, sedes, plazas, tarifas y planes; marcar interés |
| Usuario (app) | Perfil, vehículos, reservar, pagar (`app`), finalizar su sesión, suscripción, alertas, notificaciones |
| Empleado | Panel web (dashboard, reservas, pagos, clientes, reportes), confirmar, check-in/out, cobrar en caja |
| Cajero / Administrador | Lo anterior + reembolsos |
| Administrador | Lo anterior + sedes, espacios, tarifas y empleados |

## Endpoints por pantalla

**App móvil**

| Pantalla | Endpoint |
|---|---|
| Login / Registro | `POST /auth/usuarios/login` · `POST /auth/usuarios/registro` |
| Inicio | `GET /reservas/mias/resumen` (próximas, vehículos, sesión activa, plan, notificaciones sin leer) |
| Mapa GPS | `GET /parqueaderos/cercanos?latitud&longitud&radio_km&tipo&q` (distancia, $/h desde, libres, interesados) |
| Nueva reserva | `GET /espacios/zonas?sede_id` · `GET /tarifas?sede_id` |
| Selecciona tu plaza | `GET /espacios/plazas?sede_id&fecha_inicio&fecha_fin&zona` (`estado_horario`, `interesados`) |
| Confirmación | `POST /reservas` (código `Rsv-000123`, total estimado) |
| Pre-pago | `POST /reservas/{id}/pagos` con `metodo_pago: app` → al cubrir el total queda `confirmada` |
| Mis reservas | `GET /reservas/mias?estado=pendiente&estado=confirmada` · `completada` · `cancelada` |
| Sesión activa | `GET /reservas/{id}` · `POST /reservas/{id}/salida` (Finalizar sesión) |
| Mis vehículos / Perfil | `GET/PATCH /usuarios/me` · `POST/DELETE /usuarios/me/vehiculos` |
| Planes / Afiliado | `GET /suscripciones/planes` · `POST /suscripciones` · `GET /suscripciones/mia` · `POST /suscripciones/mia/cancelar` |
| Alertas de cupo | `GET/POST /alertas` · `DELETE /alertas/{id}` (solo Afiliado) |
| Notificaciones 🔔 | `GET /notificaciones` · `POST /notificaciones/{id}/leer` · `POST /notificaciones/leer-todas` |
| Interés en vivo | `POST /sedes/{sede_id}/interes` cada ~60 s mientras la sede esté en pantalla |

**Panel web**

| Sección | Endpoint |
|---|---|
| Login | `POST /auth/empleados/login` |
| Dashboard | `GET /admin/dashboard?sede_id` |
| Reservas | `GET /reservas?q&estado&zona&sede_id&desde&hasta` · `GET /admin/reservas/estadisticas?fecha` · `GET /admin/reservas/exportar` |
| Operación | `GET /espacios/plazas` · `PATCH /espacios/{id}` · `POST /reservas/check-in-manual` · `POST /reservas/check-out-manual` · `POST /reservas/{id}/entrada\|salida\|confirmar\|cancelar` |
| Pagos | `GET /admin/pagos?desde&hasta&metodo_pago&estado` · `GET /admin/pagos/resumen?fecha` · `POST /reservas/{id}/pagos` · `POST /reservas/{id}/reembolsos` · `GET /admin/pagos/exportar` |
| Clientes / Vehículos | `GET /admin/clientes?q` · `GET /admin/vehiculos?q` |
| Tarifas | `GET/POST /tarifas` · `PATCH/DELETE /tarifas/{id}` |
| Reportes | `GET /admin/reportes?desde&hasta` (ingresos por día/método/zona, horas pico, duración promedio, cancelación) |
| Usuarios (empleados) | `GET/POST /empleados` · `PATCH /empleados/{id}` |
| Sedes y Zonas | `POST /parqueaderos/{id}/sedes` · `PATCH /parqueaderos/{id}/sedes/{sede_id}` · `POST /espacios` |
| Configuración | `PATCH /parqueaderos/{id}` |
| Actividad reciente | `GET /admin/actividad` |

Las fechas de `/admin` (`fecha`, `desde`, `hasta`) son días en hora de Colombia (`ZONA_HORARIA`).

## Tiempo real

`ws://<host>/api/v1/ws/sedes/{sede_id}` envía cada evento de la sede:

```json
{"evento": "check_in", "espacio_id": "…", "estado_espacio": "ocupado",
 "descripcion": "ABC123 en Zona A - Plaza A-12", "reserva_id": "…", "fecha": "…"}
```

Eventos: `reserva_creada`, `reserva_confirmada`, `reserva_cancelada`, `reserva_vencida`, `check_in`,
`check_out`, `pago`, `reembolso`, `espacio_estado` e `interes` (`{"viendo": 3, "por_espacio": {...}}`).

Sin Redis funciona con **un proceso**. Para varios workers o instancias, define `REDIS_URL`
(Redis local, Redis Cloud o Upstash): cada proceso publica en Redis y todos reenvían a sus clientes.

## Reglas de negocio

- **Ciclo de una reserva:** `pendiente` → (pago completo o `confirmar`) → `confirmada` → `entrada`
  (plaza `ocupado`) → `salida` (plaza `disponible`, `completada`). Se cobra por hora o fracción,
  con un mínimo de 1 h, usando la `tarifa_aplicada` que se copia al reservar.
- **Vencimiento:** una reserva `pendiente` sin ningún pago se cancela sola a los
  `RESERVA_PENDIENTE_MINUTOS` (15). Los afiliados tienen `RESERVA_PENDIENTE_MINUTOS_AFILIADO` (60).
- **Plan Afiliado** ($29.900/mes):
  - `AFILIADO_DESCUENTO_PCT` (15%) de descuento en la tarifa.
  - En hora pico, el último `AFILIADO_CUPO_PRIORITARIO_PCT` (10%) de las plazas libres queda solo para afiliados.
  - Alertas cuando se libera un cupo.
  - Renovación automática cada 30 días.
- **Walk-in:** si llega un vehículo sin cuenta, `check-in-manual` crea un cliente ocasional con su placa.
  Si esa persona se registra después con otra placa, no se vinculan solas.
- **Reembolsos:** se guardan como pagos con `estado: reembolsado` y restan de `total_pagado`.

## Cambios al modelo original (para Moon Modeler)

- `usuarios.password_hash` y `empleados.password_hash`: para el login.
- `sedes[].ubicacion`: GeoJSON `Point [longitud, latitud]`, para el mapa.
- `reservas.codigo` (`Rsv-000123`), `reservas.tarifa_aplicada.descuento_pct`, `reservas.pagos[].codigo` (`TX-000045`),
  y el estado de pago `reembolsado`.
- Colecciones nuevas:
  - `contadores`: secuencias para los códigos.
  - `actividad`: historial del panel; se borra solo a los 90 días.
  - `suscripciones`.
  - `notificaciones`.
  - `alertas_cupo`.
  - `interesados`: quién está viendo una sede; expira a los 2 min.

## Tests

Usan `mongomock-motor` y `fakeredis`, así que no necesitan Atlas ni Redis:

```bash
pytest
```

## Pendiente para producción

- **Pasarela de pagos real** (Wompi, ePayco o Mercado Pago). Hoy los pagos por `app` y las suscripciones
  se aprueban sin cobrar; están marcados con `TODO`.
- **Notificaciones push** con Firebase Cloud Messaging. Hoy las notificaciones solo se guardan en la base.
- **Recuperar contraseña y refresh tokens.** El token dura `ACCESS_TOKEN_EXPIRE_MINUTES`.
# ParkingPro-backend
# ParkingPro-backend
# ParkingPro-backend
