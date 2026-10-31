from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "ParkingPro API"
    DEBUG: bool = False

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "parkingpro"
    REDIS_URL: Optional[str] = None  # opcional: tiempo real entre varios procesos/instancias

    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    BCRYPT_ROUNDS: int = 12

    CORS_ORIGINS: List[str] = ["*"]
    SEED_PASSWORD: str = "parkingpro123"

    # Operación
    ZONA_HORARIA: str = "America/Bogota"
    RESERVA_PENDIENTE_MINUTOS: int = 15  # tiempo para pagar una reserva antes de que venza
    RESERVA_PENDIENTE_MINUTOS_AFILIADO: int = 60
    TAREAS_PERIODICAS: bool = True  # vencer reservas/suscripciones cada minuto

    # Plan Afiliado
    AFILIADO_PRECIO_MENSUAL: int = 29900
    AFILIADO_DESCUENTO_PCT: int = 15
    AFILIADO_CUPO_PRIORITARIO_PCT: int = 10  # % de plazas reservado a afiliados en hora pico

    # Política por defecto para socios y parqueaderos nuevos. Se copia al crearlos: cambiarla
    # después solo afecta a los nuevos. Valores provisionales hasta que el equipo los defina.
    COMISION_PCT: int = 10
    COMISION_PRUEBA_PCT: int = 0  # 0 = no se cobra comisión durante la prueba
    PRUEBA_DIAS: int = 30
    LIMITE_DEUDA: int = 500000  # pesos
    DEUDA_DIAS_GRACIA: int = 7


settings = Settings()
