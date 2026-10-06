import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


# El envío real (SMTP) es el siguiente paso. Hoy queda en el log.
# El token de recuperación solo se imprime con DEBUG, para poder probarlo en local.

async def send_welcome_email(email: str, nombre: str) -> None:
    logger.info("Enviando email de bienvenida a %s (%s)", email, nombre)


async def send_reserva_email(email: str, reserva_id: str, evento: str) -> None:
    logger.info("Notificando a %s: reserva %s %s", email, reserva_id, evento)


async def send_password_reset_email(email: str, nombre: str, token: str) -> None:
    logger.info("Correo de recuperación de contraseña para %s (%s)", email, nombre)
    if settings.DEBUG:
        logger.info("Token de recuperación (solo DEBUG) para %s", token)
