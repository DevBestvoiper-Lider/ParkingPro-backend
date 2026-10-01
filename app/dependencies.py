from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import get_db
from app.core.realtime import HubTiempoReal, hub
from app.core.security import decode_access_token
from app.core.utils import parse_oid
from app.repositories.actividad_repository import ActividadRepository
from app.repositories.alerta_repository import AlertaRepository
from app.repositories.base import Document
from app.repositories.contador_repository import ContadorRepository
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.espacio_repository import EspacioRepository
from app.repositories.interes_repository import InteresRepository
from app.repositories.notificacion_repository import NotificacionRepository
from app.repositories.parqueadero_repository import ParqueaderoRepository
from app.repositories.reserva_repository import ReservaRepository
from app.repositories.suscripcion_repository import SuscripcionRepository
from app.repositories.tarifa_repository import TarifaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import Principal
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.empleado_service import EmpleadoService
from app.services.espacio_service import EspacioService
from app.services.eventos import Eventos
from app.services.interes_service import InteresService
from app.services.mapa_service import MapaService
from app.services.notificacion_service import NotificacionService
from app.services.parqueadero_service import ParqueaderoService
from app.services.reserva_service import ReservaService
from app.services.suscripcion_service import SuscripcionService
from app.services.tarifa_service import TarifaService
from app.services.usuario_service import UsuarioService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/usuarios/login")
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/usuarios/login", auto_error=False)


# --- Repositories ---
def get_parqueadero_repository(db: AsyncDatabase = Depends(get_db)) -> ParqueaderoRepository:
    return ParqueaderoRepository(db)


def get_empleado_repository(db: AsyncDatabase = Depends(get_db)) -> EmpleadoRepository:
    return EmpleadoRepository(db)


def get_usuario_repository(db: AsyncDatabase = Depends(get_db)) -> UsuarioRepository:
    return UsuarioRepository(db)


def get_espacio_repository(db: AsyncDatabase = Depends(get_db)) -> EspacioRepository:
    return EspacioRepository(db)


def get_tarifa_repository(db: AsyncDatabase = Depends(get_db)) -> TarifaRepository:
    return TarifaRepository(db)


def get_reserva_repository(db: AsyncDatabase = Depends(get_db)) -> ReservaRepository:
    return ReservaRepository(db)


def get_contador_repository(db: AsyncDatabase = Depends(get_db)) -> ContadorRepository:
    return ContadorRepository(db)


def get_actividad_repository(db: AsyncDatabase = Depends(get_db)) -> ActividadRepository:
    return ActividadRepository(db)


def get_suscripcion_repository(db: AsyncDatabase = Depends(get_db)) -> SuscripcionRepository:
    return SuscripcionRepository(db)


def get_notificacion_repository(db: AsyncDatabase = Depends(get_db)) -> NotificacionRepository:
    return NotificacionRepository(db)


def get_alerta_repository(db: AsyncDatabase = Depends(get_db)) -> AlertaRepository:
    return AlertaRepository(db)


def get_interes_repository(db: AsyncDatabase = Depends(get_db)) -> InteresRepository:
    return InteresRepository(db)


def get_hub() -> HubTiempoReal:
    return hub


# --- Services ---
def get_auth_service(
    usuarios: UsuarioRepository = Depends(get_usuario_repository),
    empleados: EmpleadoRepository = Depends(get_empleado_repository),
) -> AuthService:
    return AuthService(usuarios, empleados)


def get_usuario_service(repo: UsuarioRepository = Depends(get_usuario_repository)) -> UsuarioService:
    return UsuarioService(repo)


def get_parqueadero_service(
    repo: ParqueaderoRepository = Depends(get_parqueadero_repository),
    empleados: EmpleadoRepository = Depends(get_empleado_repository),
) -> ParqueaderoService:
    return ParqueaderoService(repo, empleados)


def get_empleado_service(repo: EmpleadoRepository = Depends(get_empleado_repository)) -> EmpleadoService:
    return EmpleadoService(repo)


def get_eventos(
    actividad: ActividadRepository = Depends(get_actividad_repository),
    hub: HubTiempoReal = Depends(get_hub),
) -> Eventos:
    return Eventos(actividad, hub)


def get_notificacion_service(
    repo: NotificacionRepository = Depends(get_notificacion_repository),
    alertas: AlertaRepository = Depends(get_alerta_repository),
) -> NotificacionService:
    return NotificacionService(repo, alertas)


def get_espacio_service(
    repo: EspacioRepository = Depends(get_espacio_repository),
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
    reservas: ReservaRepository = Depends(get_reserva_repository),
    interesados: InteresRepository = Depends(get_interes_repository),
    eventos: Eventos = Depends(get_eventos),
) -> EspacioService:
    return EspacioService(repo, parqueaderos, reservas, interesados, eventos)


def get_tarifa_service(
    repo: TarifaRepository = Depends(get_tarifa_repository),
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
) -> TarifaService:
    return TarifaService(repo, parqueaderos)


def get_reserva_service(
    repo: ReservaRepository = Depends(get_reserva_repository),
    espacios: EspacioRepository = Depends(get_espacio_repository),
    tarifas: TarifaRepository = Depends(get_tarifa_repository),
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
    usuarios: UsuarioRepository = Depends(get_usuario_repository),
    contadores: ContadorRepository = Depends(get_contador_repository),
    suscripciones: SuscripcionRepository = Depends(get_suscripcion_repository),
    eventos: Eventos = Depends(get_eventos),
    notificaciones: NotificacionService = Depends(get_notificacion_service),
) -> ReservaService:
    return ReservaService(
        repo, espacios, tarifas, parqueaderos, usuarios, contadores, suscripciones, eventos, notificaciones
    )


def get_mapa_service(
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
    espacios: EspacioRepository = Depends(get_espacio_repository),
    tarifas: TarifaRepository = Depends(get_tarifa_repository),
    reservas: ReservaRepository = Depends(get_reserva_repository),
    interesados: InteresRepository = Depends(get_interes_repository),
) -> MapaService:
    return MapaService(parqueaderos, espacios, tarifas, reservas, interesados)


def get_interes_service(
    repo: InteresRepository = Depends(get_interes_repository),
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
    espacios: EspacioRepository = Depends(get_espacio_repository),
    hub: HubTiempoReal = Depends(get_hub),
) -> InteresService:
    return InteresService(repo, parqueaderos, espacios, hub)


def get_suscripcion_service(
    repo: SuscripcionRepository = Depends(get_suscripcion_repository),
    alertas: AlertaRepository = Depends(get_alerta_repository),
    parqueaderos: ParqueaderoRepository = Depends(get_parqueadero_repository),
) -> SuscripcionService:
    return SuscripcionService(repo, alertas, parqueaderos)


def get_admin_service(
    reservas: ReservaRepository = Depends(get_reserva_repository),
    espacios: EspacioRepository = Depends(get_espacio_repository),
    usuarios: UsuarioRepository = Depends(get_usuario_repository),
    suscripciones: SuscripcionRepository = Depends(get_suscripcion_repository),
    actividad: ActividadRepository = Depends(get_actividad_repository),
    reserva_service: ReservaService = Depends(get_reserva_service),
) -> AdminService:
    return AdminService(reservas, espacios, usuarios, suscripciones, actividad, reserva_service)


# --- Auth ---
async def get_principal(
    token: str = Depends(oauth2_scheme),
    usuarios: UsuarioRepository = Depends(get_usuario_repository),
    empleados: EmpleadoRepository = Depends(get_empleado_repository),
) -> Principal:
    no_autorizado = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    subject = decode_access_token(token) or ""
    tipo, _, raw_id = subject.partition(":")
    if tipo == "usuario":
        doc = await usuarios.get(parse_oid(raw_id))
    elif tipo == "empleado":
        doc = await empleados.get(parse_oid(raw_id), estado="activo")
    else:
        raise no_autorizado
    if doc is None:
        raise no_autorizado
    return Principal(tipo, doc)


async def get_principal_opcional(
    token: Optional[str] = Depends(oauth2_opcional),
    usuarios: UsuarioRepository = Depends(get_usuario_repository),
    empleados: EmpleadoRepository = Depends(get_empleado_repository),
) -> Optional[Principal]:
    """Para endpoints públicos que se comportan distinto si hay sesión (ej. invitado vs usuario)."""
    if not token:
        return None
    return await get_principal(token, usuarios, empleados)


async def get_current_usuario(principal: Principal = Depends(get_principal)) -> Document:
    if not principal.es_usuario:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para usuarios de la app")
    return principal.doc


async def get_current_empleado(principal: Principal = Depends(get_principal)) -> Document:
    if not principal.es_empleado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para empleados del parqueadero")
    return principal.doc


async def get_current_admin(empleado: Document = Depends(get_current_empleado)) -> Document:
    if empleado["rol"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol administrador")
    return empleado


def require_roles(*roles: str):
    async def dependencia(empleado: Document = Depends(get_current_empleado)) -> Document:
        if empleado["rol"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requiere rol: {', '.join(roles)}")
        return empleado
    return dependencia
