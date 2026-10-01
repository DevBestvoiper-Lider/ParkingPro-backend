from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import get_auth_service, get_usuario_service
from app.schemas.auth import Token
from app.schemas.usuario import UsuarioCreate, UsuarioRead
from app.services.auth_service import AuthService
from app.services.usuario_service import UsuarioService
from app.tasks.background import send_welcome_email

router = APIRouter(prefix="/auth", tags=["auth"])


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
