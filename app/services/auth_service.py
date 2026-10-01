from fastapi import HTTPException, status

from app.core.security import create_access_token, verify_password
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import Token

CREDENCIALES_INVALIDAS = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")


class AuthService:
    def __init__(self, usuarios: UsuarioRepository, empleados: EmpleadoRepository):
        self.usuarios = usuarios
        self.empleados = empleados

    async def login_usuario(self, email: str, password: str) -> Token:
        usuario = await self.usuarios.get_by_email(email)
        if not usuario or not verify_password(password, usuario.get("password_hash", "")):
            raise CREDENCIALES_INVALIDAS
        return Token(access_token=create_access_token(f"usuario:{usuario['_id']}"), tipo="usuario")

    async def login_empleado(self, email: str, password: str) -> Token:
        empleado = await self.empleados.get_by_email(email)
        if not empleado or not verify_password(password, empleado.get("password_hash", "")):
            raise CREDENCIALES_INVALIDAS
        if empleado["estado"] != "activo":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Empleado inactivo")
        return Token(access_token=create_access_token(f"empleado:{empleado['_id']}"), tipo="empleado")
