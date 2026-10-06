import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_jwt, hash_password, verify_password
from app.core.utils import utcnow
from app.repositories.base import BaseRepository, Document
from app.repositories.empleado_repository import EmpleadoRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import TipoCuenta, Token

CREDENCIALES_INVALIDAS = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Credenciales inválidas",
    headers={"WWW-Authenticate": "Bearer"},
)
RESET_INVALIDO = HTTPException(
    status.HTTP_400_BAD_REQUEST,
    "El enlace de recuperación no es válido o ya venció",
)


class AuthService:
    def __init__(self, usuarios: UsuarioRepository, empleados: EmpleadoRepository):
        self.usuarios = usuarios
        self.empleados = empleados

    async def login_usuario(self, email: str, password: str) -> Token:
        usuario = await self.usuarios.get_by_email(email)
        if not usuario or not verify_password(password, usuario.get("password_hash", "")):
            raise CREDENCIALES_INVALIDAS
        return self._emitir("usuario", usuario)

    async def login_empleado(self, email: str, password: str) -> Token:
        empleado = await self.empleados.get_by_email(email)
        if not empleado or not verify_password(password, empleado.get("password_hash", "")):
            raise CREDENCIALES_INVALIDAS
        if empleado["estado"] != "activo":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Empleado inactivo")
        return self._emitir("empleado", empleado)

    async def refrescar(self, refresh_token: str) -> Token:
        payload = decode_jwt(refresh_token)
        if not payload or payload.get("typ") != "refresh" or not payload.get("sub"):
            raise CREDENCIALES_INVALIDAS
        tipo, _, raw_id = str(payload["sub"]).partition(":")
        if tipo not in ("usuario", "empleado") or not ObjectId.is_valid(raw_id):
            raise CREDENCIALES_INVALIDAS
        tipo_cuenta: TipoCuenta = "usuario" if tipo == "usuario" else "empleado"
        repo = self.usuarios if tipo_cuenta == "usuario" else self.empleados
        doc = await repo.get(ObjectId(raw_id))
        if not doc or doc.get("sesion_version", 0) != payload.get("ver", 0):
            raise CREDENCIALES_INVALIDAS
        if tipo_cuenta == "empleado" and doc.get("estado") != "activo":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Empleado inactivo")
        return self._emitir(tipo_cuenta, doc)

    async def solicitar_recuperacion(self, email: str) -> Optional[Tuple[str, str, str]]:
        """(email, nombre, token) si hay una cuenta con clave. None si no, sin decir cuál fue el caso."""
        cuenta = await self._cuenta_con_clave(email)
        if not cuenta:
            return None
        _, repo, doc = cuenta
        token = secrets.token_urlsafe(32)
        await repo.update(doc["_id"], {
            "reset_token_hash": _hash_token(token),
            "reset_expira": utcnow() + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        })
        return doc["email"], doc["nombre"], token

    async def restablecer(self, token: str, password: str) -> None:
        token_hash = _hash_token(token)
        ahora = utcnow()
        for repo in (self.usuarios, self.empleados):
            doc = await repo.collection.find_one({
                "reset_token_hash": token_hash,
                "reset_expira": {"$gt": ahora},
            })
            if not doc:
                continue
            await repo.update(
                doc["_id"],
                {
                    "password_hash": hash_password(password),
                    "sesion_version": doc.get("sesion_version", 0) + 1,
                },
                unset=["reset_token_hash", "reset_expira"],
            )
            return
        raise RESET_INVALIDO

    async def _cuenta_con_clave(self, email: str) -> Optional[Tuple[str, BaseRepository, Document]]:
        email = email.lower()
        usuario = await self.usuarios.get_by_email(email)
        if usuario and usuario.get("password_hash"):
            return "usuario", self.usuarios, usuario
        empleado = await self.empleados.get_by_email(email)
        if empleado and empleado.get("password_hash") and empleado.get("estado") == "activo":
            return "empleado", self.empleados, empleado
        return None

    @staticmethod
    def _emitir(tipo: TipoCuenta, doc: Document) -> Token:
        version = int(doc.get("sesion_version", 0))
        subject = f"{tipo}:{doc['_id']}"
        return Token(
            access_token=create_access_token(subject, version=version),
            refresh_token=create_refresh_token(subject, version=version),
            tipo=tipo,
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
