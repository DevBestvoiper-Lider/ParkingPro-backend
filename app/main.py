import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_client, get_db
from app.core.realtime import hub
from app.models.collections import ensure_indexes
from app.routers import (
    admin, auth, empleados, espacios, notificaciones, parqueaderos, reservas, socios, suscripciones, tarifas,
    tiempo_real, usuarios,
)
from app.tasks.jobs import ejecutar_periodicamente

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    await db.command("ping")
    await ensure_indexes(db)
    await hub.iniciar(settings.REDIS_URL)
    tareas = asyncio.create_task(ejecutar_periodicamente(db, hub)) if settings.TAREAS_PERIODICAS else None
    yield
    if tareas:
        tareas.cancel()
        with suppress(asyncio.CancelledError):
            await tareas
    await hub.detener()
    await close_client()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# "API Gateway": todas las rutas se agrupan bajo /api/v1
api_router = APIRouter(prefix="/api/v1")
for module in (
    auth, usuarios, socios, parqueaderos, empleados, espacios, tarifas, reservas, suscripciones, notificaciones,
    tiempo_real, admin,
):
    api_router.include_router(module.router)
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
