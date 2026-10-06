# Contexto del proyecto ParkingPro

Documento para retomar el trabajo sin depender de conversaciones anteriores. El detalle técnico
de endpoints, arranque y reglas de negocio está en [README.md](README.md); aquí va el **porqué**,
el estado y lo que sigue.

_Última actualización: 2026-10-05_

## Qué es

**ParkingPro**: aplicación móvil (Android/iOS) y plataforma web para buscar, reservar y pagar
parqueaderos disponibles en tiempo real en **Cartagena de Indias**.

- **Tipo:** proyecto de aula de Tecnología en Desarrollo de Software (V/VI semestre, clase 2311).
  Fundación Universitaria Tecnológico Comfenalco.
- **Docente:** Pedro José Jiménez Díaz.
- **Equipo:** Esteban García, Kevin Gonzalez, Luis Sandon y Jesus Ayola.
- **Metodología:** Scrum. Se articula con Ingeniería de Software, Minería de Datos I e Innovación y Emprendimiento.
- **Mockup** (pantallas móviles, panel web y flujo de navegación): https://claude.ai/artifact/9gAX9xjJTZorAiYUQXbLRz

### Funcionalidades de la propuesta y dónde quedaron

| Propuesta | Estado en el backend |
|---|---|
| Búsqueda de disponibilidad en tiempo real | ✅ `GET /parqueaderos/cercanos` + WebSocket por sede |
| Ruta más cercana | ✅ El backend da coordenadas y distancia; **la ruta la traza la app** (Google Maps / OSRM) |
| Vista del área específica (piso/zona/plaza) | ✅ Zonas + `GET /espacios/plazas` con estado por horario |
| Tiempo de ocupación | ✅ `sesion.hora_entrada` + `total` calculado en vivo |
| Interés / visualización simultánea | ✅ `POST /sedes/{id}/interes` (expira a los 2 min) |
| Reserva por tiempo estimado | ✅ `fecha_inicio` / `fecha_fin` |
| Pago desde el teléfono | ⚠️ Flujo completo, pero **cobro simulado** (falta pasarela) |
| Pre-pago remoto | ✅ Pagar el total confirma la reserva y asegura el espacio |
| Plan por uso / Plan Afiliado | ✅ Descuento, prioridad en hora pico, alertas de cupo, soporte prioritario (solo texto) |
| Panel administrativo (dashboard, reservas, operación, pagos, clientes, vehículos, tarifas, reportes, usuarios, sedes y zonas, configuración) | ✅ Todas las secciones del mockup |

## Estado actual

- **Backend: completo y desplegado.** El código está en `/Users/Luis_Sandon/flutter/backend` y tiene 30 tests pasando.
  - **Servidor (desde 2026-10-01):** `http://bestcontactcenter.bestvoiper.com:8000` (Swagger en `/docs`).
    Se verificaron salud, rutas, datos del demo, login y WebSocket.
  - **Sin HTTPS todavía** (ver "Pendiente para producción").
- **Frontend: en construcción.** Está en `/Users/Luis_Sandon/flutter/app` (paquete `parkingpro`, org `co.parkingpro`,
  plataformas android, ios y web). Tiene 26 tests pasando.
  - **Hechas:** Bienvenida, Login, Registro, Inicio, Perfil, Mapa GPS y el flujo de reserva completo, más la barra inferior.
    Verificadas en el simulador de iOS contra Atlas; la release está instalada en el iPhone de Luis.
  - **Pendientes:** el resto de pantallas; hoy muestran "Próximamente".
  - Su `CLAUDE.md` importa este archivo.
- **Base de datos:** MongoDB Atlas, base `parkingpro` (cluster `misgastos.t3vagzx.mongodb.net`), con dos juegos de datos:
  - Los datos de ejemplo del script original del equipo (Sede Chapinero, Bogotá).
  - El **demo de Cartagena**: 2 parqueaderos, 4 sedes, 240 plazas, 6 clientes y ~52 reservas.
- **Credenciales:** están en `.env`, que está en `.gitignore`. **Nunca pegarlas en chats ni commits.**
  La contraseña de Atlas quedó expuesta en una sesión de trabajo del 2026-09-30, así que conviene rotarla
  en *Database Access* si no se ha hecho.

### Usuarios demo (contraseña = `SEED_PASSWORD` del `.env`)

| Rol | Email |
|---|---|
| Admin panel web | `admin@demo.parkingpro.co` |
| Operador / Cajero | `operador@demo.parkingpro.co` / `cajero@demo.parkingpro.co` |
| App, plan Afiliado, con sesión activa | `carlos.perez@demo.parkingpro.co` |
| App, plan por uso | `maria.gomez@demo.parkingpro.co` |
| Admin del parqueadero de ejemplo original | `laura.gomez@parkingprocentro.com` |

## Stack y decisiones técnicas

| Decisión | Por qué |
|---|---|
| **FastAPI**, arquitectura Routers → Services → Repositories | Pedido del equipo: la distribución de carpetas de la imagen de referencia (routers, services, repositories, schemas, models, dependencies.py, background tasks, external APIs) |
| **MongoDB Atlas** en vez de Postgres | El equipo ya tenía el modelo en Mongo con validadores `$jsonSchema` (diseñado en Moon Modeler) |
| Driver **PyMongo async** (`AsyncMongoClient`), no Motor | Motor está deprecado |
| `models/` guarda validadores, índices y enums (no ORM) | En Mongo no hay ORM; así la carpeta conserva su sentido y el esquema queda versionado en código |
| Documentos **embebidos**: sedes en parqueaderos, vehículos en usuarios, sesión y pagos en reservas | Así venía el modelo original del equipo |
| `tarifa_aplicada` se **copia** en la reserva | Si cambia el precio, las reservas conservan el suyo |
| Dinero como `Decimal128` en Mongo y número en el JSON | Precisión exacta en la base; cómodo para Flutter |
| Fechas en UTC en la base y en la API; los reportes usan días de **America/Bogota** | Evita errores de zona horaria |
| Distancia del mapa calculada **en Python (haversine)**, no con `$geoNear` | mongomock (tests) no soporta consultas geográficas. A escala de ciudad sobra; con miles de sedes, migrar a índice 2dsphere |
| Estadísticas del panel calculadas **en Python**, no con aggregate | Más simple y testeable a esta escala; migrar a aggregate si crece el volumen |
| **Redis opcional** (`REDIS_URL`), solo para pub/sub del WebSocket | Sin Redis funciona con 1 proceso. No se usa como caché: podría mostrar plazas libres que ya están ocupadas |
| Tareas periódicas **dentro de la API** (cada 60 s) | Evita otro servicio. Son idempotentes (updates condicionales), así que no se duplican con varios procesos |
| Tests con **mongomock-motor** y **fakeredis** | No necesitan Atlas ni Redis |
| bcrypt con `BCRYPT_ROUNDS` configurable (12 en prod, 4 en tests) | Los tests eran lentísimos con el equipo cargado |
| Python **3.9** (el del sistema) | Es lo instalado en el Mac. El código usa `Optional`/`List`, no `X \| None`. El Dockerfile usa 3.12 |

## Modelo de datos

Las colecciones originales del equipo son `parqueaderos`, `empleados`, `usuarios`, `espacios_parqueo`,
`tarifas` y `reservas`.

**Cambios agregados**, que hay que reflejar en Moon Modeler:

- `usuarios.password_hash` y `empleados.password_hash`: login.
- `sesion_version`, `reset_token_hash` y `reset_expira` en usuarios y empleados: el refresh token
  lleva la versión, y al cambiar la clave sube. El enlace de recuperación guarda solo el hash y vence a los 30 min.
- `parqueaderos.sedes[].ubicacion`: GeoJSON `Point [longitud, latitud]`, para el mapa.
- `reservas.codigo`: `Rsv-000123`.
- `reservas.tarifa_aplicada.descuento_pct`: plan Afiliado.
- `reservas.pagos[].codigo` (`TX-000045`), y el estado de pago nuevo `reembolsado`.
- Colecciones nuevas:
  - `contadores`: secuencias para los códigos.
  - `actividad`: historial del panel, TTL de 90 días.
  - `suscripciones`.
  - `notificaciones`.
  - `alertas_cupo`.
  - `interesados`: TTL; quién está viendo una sede.

Los validadores viven en `app/models/collections.py`. Para aplicarlos en Atlas corre
`python -m scripts.init_db`; el script también asigna códigos a reservas viejas sin código.

> **Regla del equipo:** el modelo de datos es un entregable del curso. **Consultar antes de agregar
> campos o colecciones**, y documentar cada cambio aquí y en el README.

## Reglas de negocio clave

(El detalle está en el README, sección "Reglas de negocio".)

- **Ciclo de una reserva:** `pendiente` → `confirmada` (por pago completo o porque un empleado la confirma)
  → entrada (plaza `ocupado`) → salida (plaza `disponible`, `completada`).
- **Cobro:** por hora o fracción, mínimo 1 h.
- **Vencimiento:** una reserva pendiente **sin ningún pago** se cancela sola a los 15 min (60 para afiliados).
  Si tiene un abono, no se cancela sola.
- **Plan Afiliado** ($29.900/mes):
  - 15% de descuento.
  - En hora pico, el último 10% de las plazas queda solo para afiliados.
  - Alertas de cupo.
  - 60 min para pagar una reserva.
- **Salida:** la puede registrar un empleado o el propio usuario ("Finalizar sesión").
- **Métodos de pago:** el usuario solo paga con `app`; en caja se cobra con `efectivo` o `tarjeta`.
  Los reembolsos los hace el administrador o el cajero.
- **Walk-in:** si llega un vehículo sin cuenta, se crea un "cliente ocasional" con su placa y sin acceso a la app.

## Pendiente para producción

1. **Pasarela de pagos real** (Wompi, ePayco o Mercado Pago). Hoy se aprueban sin cobrar los pagos `app`
   y las suscripciones; están marcados con `TODO` en `reserva_service.py`, `suscripcion_service.py`
   y `tasks/jobs.py`.
2. **Notificaciones push** con Firebase Cloud Messaging. Hoy solo se guardan en la base
   (`TODO` en `notificacion_service.py`).
3. **Vincular walk-in con registro posterior:** si un cliente ocasional se registra luego con su placa,
   hoy no se unen sus historiales.
4. **Emails reales.** `tasks/background.py` solo escribe en el log. Con `DEBUG=true` imprime el token
   de recuperación para poder probar el flujo sin correo.
5. **HTTPS en el servidor.** Hoy la API va por HTTP en `bestcontactcenter.bestvoiper.com:8000`, así que el
   token y las contraseñas viajan sin cifrar. Para que la app funcione se agregaron excepciones solo para
   `bestvoiper.com`: `NSExceptionDomains` en `ios/Runner/Info.plist` y `res/xml/network_security_config.xml`
   en Android. Con HTTPS (por ejemplo, Caddy o nginx con Let's Encrypt delante de uvicorn):
   - Cambiar `Env.servidor` a `https://…` (y el WebSocket pasa solo a `wss://`).
   - Quitar esas excepciones.

## Próximos pasos: frontend en Flutter

Acordado con el equipo: **primero el backend al 100% (hecho), luego el frontend.**

- **Dónde:** `/Users/Luis_Sandon/flutter/app`. Flutter 3.47.5.
- **Un proyecto para ambos frentes:** la app móvil (Android/iOS) y el panel web (Flutter Web)
  salen del mismo proyecto.

### Decisiones del frontend (2026-09-30)

| Decisión | Por qué |
|---|---|
| **Riverpod 3** (sin generación de código) | Estado reactivo y testeable; sin `build_runner`, más simple para el equipo |
| **go_router** con `StatefulShellRoute` | Barra inferior que conserva el estado de cada pestaña; redirecciones según la sesión |
| **Dio** + `ApiException` | Interceptor que agrega el token y, si la API responde 401, cierra la sesión. Los errores de FastAPI (`detail`) se traducen a un mensaje para el usuario |
| **flutter_secure_storage** para el token | Keychain (iOS) / Keystore (Android), no texto plano |
| **flutter_map + OpenStreetMap** (a usar en el Mapa) | Gratis y sin API key. Si luego quieren Google Maps, solo cambia esa pantalla |
| **google_fonts ^8** (fuente Inter, como el mockup) | La versión 9 usa `material_ui` y no es compatible con `flutter/material` en Flutter 3.47 |
| Organización **por funcionalidad**: `lib/features/<x>/{data,domain,presentation}` + `lib/core` | Cada pantalla tiene su repositorio (llama a la API), sus modelos y su UI |

### Estructura

```
lib/
├── main.dart / app.dart        # ProviderScope, tema y router
├── core/                       # config (URL de la API), network (Dio, ApiException), storage (token),
│                               # theme (colores del mockup), router, utils (formatos $ y hora), widgets
└── features/
    ├── auth/      # Bienvenida, Login, Registro, AuthController (sesión: null / invitado / usuario)
    ├── home/      # Inicio (resumen, acciones rápidas, sesión activa con cronómetro)
    ├── reservas/  # Modelos Reserva y ResumenUsuario + repositorio
    ├── perfil/    # Perfil y cerrar sesión
    └── shell/     # Barra inferior
test/              # unit_test (errores, formatos, modelos) y flujo_test (navegación con repos falsos)
```

### Cómo correrlo

```bash
cd /Users/Luis_Sandon/flutter/app
flutter run                                       # elige el simulador o emulador
flutter run -d chrome                             # panel/app en la web
flutter run --dart-define=API_URL=http://192.168.1.10:8000/api/v1   # celular físico
flutter test
```

La API debe estar corriendo (`uvicorn ... --host 0.0.0.0`).

### Problemas conocidos del entorno

- **Simulador de iOS:** un build de debug **solo corre con `flutter run` conectado**. Si se abre desde
  el ícono, se cierra al instante.
- **`flutter test` fallaba con código 137.** Era la cuarentena de macOS sobre el SDK. Se arregló con
  `xattr -dr com.apple.quarantine /opt/homebrew/share/flutter/bin/cache`.
- **Teclado del simulador en español:** al escribir texto con herramientas automáticas, la `@` sale mal.
  Hay que usar la tecla `@` del teclado de email.
- **HTTP local:** en iOS se permitió con `NSAllowsLocalNetworking` (Info.plist). En Android solo en debug,
  con `usesCleartextTraffic` en `src/debug/AndroidManifest.xml`. En producción la API debe ir por HTTPS.

### Mapa GPS (hecho)

- **Posición:** usa `geolocator`. Sin permiso o sin GPS, muestra el **centro de Cartagena** con un aviso.
- **Pines de precio** (`$4.5k/h`) con un punto de color según la disponibilidad:
  - Verde: más del 30% de plazas libres.
  - Naranja: pocas libres.
  - Rojo: lleno.
- **Buscador:** consulta la API 400 ms después de dejar de escribir.
- **Filtros:** tipo de espacio y distancia (1, 3, 5 o 10 km).
- **Botón "Ver lista · N lugares":** abre la lista con barra de ocupación.
- **Tarjeta de la sede:**
  - Precio, cupos y "N personas están viendo este lugar". Llama a `POST /sedes/{id}/interes` al abrirse
    y cada 60 s; los invitados usan un `dispositivo_id` aleatorio guardado en el llavero.
  - **Cómo llegar:** abre Apple Maps en iOS y Google Maps en Android/web con la ruta.
  - **Reservar:** al invitado le pide iniciar sesión.
- **Mosaicos:** usa el servidor público de OpenStreetMap, que **solo sirve para desarrollo**.
  En producción hay que usar un proveedor como MapTiler o Stadia, según su política de uso.
  Se muestra el crédito "© OpenStreetMap contributors".
- **Cambio en la API para el mapa:** `GET /parqueaderos/cercanos` ahora devuelve también
  `espacios_total` (plazas operativas), para calcular la ocupación.
- **Probar en el simulador:** `xcrun simctl location <udid> set 10.4225,-75.5500` pone la ubicación
  en el Centro de Cartagena.

### Flujo de reserva (hecho)

`/reservas/nueva?sede=<id>` (desde el mapa llega con la sede elegida). Son 4 pasos con barra de progreso:

1. **Nueva Reserva:**
   - Sede, vehículo (con "Agregar" en línea), tipo de espacio, fecha, hora de entrada y salida, zona y tarifa.
   - Si la salida es antes que la entrada, se toma como el día siguiente.
   - Muestra el total estimado con la regla de la API (hora o fracción, mínimo 1 h, descuento Afiliado).
2. **Selecciona tu Plaza:**
   - Grilla por zona con los colores del mockup; solo se pueden tocar las verdes. Muestra 👀 si otros miran esa plaza.
   - **En vivo por WebSocket:** si alguien toma la plaza elegida, se desmarca y avisa.
3. **Confirma tu reserva:**
   - "Pagar ahora" crea la reserva y hace el pre-pago, que la deja `confirmada`.
   - "Reservar y pagar después" la deja `pendiente`, con 15 min (60 si es Afiliado).
   - Si la API responde 409 (plaza tomada u hora pico), vuelve a la grilla.
4. **Confirmación:** código `Rsv-…`, detalle y botón "Pagar" si quedó pendiente.


### Flujo Creacion de Carro (hecho)

1. **Nuevo Carro:**
  -

### Instalar en un iPhone físico

```bash
cd /Users/Luis_Sandon/flutter/app
flutter build ios --release                           # apunta al servidor (Env.servidor)
flutter install --release -d <id-del-iphone>          # flutter devices muestra el id
```

- **URL de la API:** las versiones release usan el servidor desplegado; las de desarrollo, la API local.
  Para una release contra la Mac: `--dart-define=API_URL=http://<IP-del-Mac>:8000/api/v1`.
- **Para instalar:** el iPhone debe estar desbloqueado y conectado por cable (o en la misma red que el Mac).
- **Release, no debug:** una build de debug en un iPhone físico solo abre conectada a `flutter run`.
- **Firma:** automática con el equipo `3434FN38D7` (certificado Apple Development de Luis). Si es una cuenta
  de Apple gratuita, la app **vence a los 7 días** y hay que reinstalarla. La primera vez, en el iPhone:
  Ajustes → General → VPN y gestión de dispositivos → confiar en el desarrollador.

### Orden sugerido para las pantallas que faltan

1. Mis reservas y Sesión activa (Finalizar sesión).
2. Mis vehículos, Notificaciones y Planes.
3. Panel web (login de empleados, dashboard, operación con WebSocket, pagos, reportes).

**Pantallas móviles del mockup** y su orden en el flujo:

1. Splash / Login (incluye "Continuar como invitado").
2. Inicio.
3. Nueva reserva.
4. Selecciona tu plaza.
5. Confirmación.
6. Mis reservas (pestañas Próximas / Completadas / Canceladas).
7. Sesión activa.
8. Mapa GPS.

La barra inferior tiene Inicio, Reservas, Mapa, Mis Plazas y Perfil.

**Panel web del mockup:** Dashboard, Reservas, Operación (mapa de plazas por zona, check-in/out manual),
Pagos, Clientes, Vehículos, Tarifas, Reportes, Usuarios, Sedes y Zonas, y Configuración.

**Notas para integrar con la API:**

- **URL base:**
  - Emulador Android: `http://10.0.2.2:8000/api/v1`.
  - Simulador iOS o web: `http://localhost:8000/api/v1`.
  - Celular físico: la IP de la Mac.
- **Login:** se envía `application/x-www-form-urlencoded` con `username` (el email) y `password`.
  Responde `{access_token, refresh_token, tipo}`. El access dura 60 min; `POST /auth/refresh`
  con `{refresh_token}` devuelve otro par, sin pedir la clave. El refresh no sirve como Bearer.
  `POST /auth/recuperar` siempre responde el mismo mensaje. `POST /auth/restablecer` con el token
  del correo cambia la clave e invalida la sesión anterior.
- **Mi actividad:** `GET /reservas/mias/actividad`. Gasto de los últimos 6 meses (hora de Colombia),
  tendencia contra el mes anterior, horas, completadas, canceladas, sedes y vehículos más usados,
  promedio por visita y ahorro Afiliado. Si ninguna visita tuvo descuento, `ahorro_es_estimado` es
  true: es lo que habría ahorrado con el 15 %. No hay colección nueva.
- **Fechas:** enviarlas en ISO 8601 con zona horaria, por ejemplo `DateTime.toUtc().toIso8601String()`.
- **Interés en vivo:** llamar `POST /sedes/{id}/interes` al abrir una sede y cada ~60 s.
  Los invitados mandan un `dispositivo_id` aleatorio que la app guarda.
- **Tiempo real:** conectarse a `ws://<host>/api/v1/ws/sedes/{sede_id}` en Operación y en Selecciona tu plaza.
- **Menos llamadas:** las reservas ya traen `sede_nombre`, `zona`, `espacio_codigo`, `placa`,
  `cliente_nombre`, `total`, `total_pagado` y `saldo`.
- **Swagger** con todos los endpoints: http://localhost:8000/docs

## Cómo trabajar en este repo

- **Idioma:** español, en el código de dominio, los mensajes de error y la comunicación.
- **Tests:** correr `pytest` antes de dar algo por terminado.
- **Cambios de esquema:** van en `app/models/collections.py`, luego `python -m scripts.init_db` para aplicarlos,
  y se documentan aquí.
- **Servidor local:** `uvicorn app.main:app --reload --host 0.0.0.0`.
  Hay una configuración `api` en `.claude/launch.json`.
