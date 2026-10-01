import logging

logger = logging.getLogger(__name__)


# Simulan el envío de emails. Reemplazar por SMTP, SendGrid, Celery, etc.

async def send_welcome_email(email: str, nombre: str) -> None:
    logger.info("Enviando email de bienvenida a %s (%s)", email, nombre)


async def send_reserva_email(email: str, reserva_id: str, evento: str) -> None:
    logger.info("Notificando a %s: reserva %s %s", email, reserva_id, evento)
