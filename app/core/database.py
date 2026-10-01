from typing import Optional

import certifi
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings

_client: Optional[AsyncMongoClient] = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        options = {"tz_aware": True}
        if settings.MONGODB_URI.startswith("mongodb+srv://"):
            # Atlas usa TLS; certifi evita errores de certificados en macOS.
            options["tlsCAFile"] = certifi.where()
        _client = AsyncMongoClient(settings.MONGODB_URI, **options)
    return _client


def get_db() -> AsyncDatabase:
    return get_client()[settings.MONGODB_DB]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
