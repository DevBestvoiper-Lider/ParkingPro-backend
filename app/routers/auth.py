from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import get_auth_service, get_principal, get_usuario_service
from app.schemas.auth import Mensaje, Principal, RecuperarClave, RefreshRequest, RestablecerClave, Token
from app.schemas.usuario import UsuarioCreate, UsuarioRead
from app.services.auth_service import AuthService
from app.services.usuario_service import UsuarioService
from app.tasks.background import send_password_reset_email, send_welcome_email

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_RECUPERACION = (
    "Si el correo está registrado, enviamos instrucciones para restablecer la contraseña."
)


@router.post("/usuarios/registro", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def registrar_usuario(
    data: UsuarioCreate,
    background_tasks: BackgroundTasks,
    service: UsuarioService = Depends(get_usuario_service),
):
    usuario = await service.registrar(data)
    background_tasks.add_task(send_welcome_email, usuario["email"], usuario["nombre"])
    return usuario


# OAuth2 usa el campo "username"; aquí contiene el email.
@router.post("/usuarios/login", response_model=Token)
async def login_usuario(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    return await service.login_usuario(form.username, form.password)


@router.post("/empleados/login", response_model=Token)
async def login_empleado(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    return await service.login_empleado(form.username, form.password)


@router.post("/camara", response_model=Token)
async def sesion_camara(
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    """Abre la cámara de portería con la sesión actual si esa cuenta también es empleado."""
    return await service.sesion_camara(principal)


@router.post("/socios/login", response_model=Token)
async def login_socio(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    """Dueño de parqueaderos. Es una cuenta aparte: para parquear usa una cuenta de usuario."""
    return await service.login_socio(form.username, form.password)


@router.post("/refresh", response_model=Token)
async def refrescar_sesion(
    data: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
):
    """Renueva el access token (60 min) con el refresh token, sin pedir la clave."""
    return await service.refrescar(data.refresh_token)


@router.post("/recuperar", response_model=Mensaje)
async def recuperar_clave(
    data: RecuperarClave,
    background_tasks: BackgroundTasks,
    service: AuthService = Depends(get_auth_service),
):
    """Siempre responde igual: no dice si el correo existe."""
    datos = await service.solicitar_recuperacion(data.email)
    if datos:
        background_tasks.add_task(send_password_reset_email, *datos)
    return Mensaje(mensaje=MENSAJE_RECUPERACION)


@router.post("/restablecer", status_code=status.HTTP_204_NO_CONTENT)
async def restablecer_clave(
    data: RestablecerClave,
    service: AuthService = Depends(get_auth_service),
):
    """Cambia la clave y deja sin efecto los refresh tokens anteriores."""
    await service.restablecer(data.token, data.password)
