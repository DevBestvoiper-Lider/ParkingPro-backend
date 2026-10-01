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


settings = Settings()
