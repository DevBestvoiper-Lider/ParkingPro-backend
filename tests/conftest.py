import os

os.environ["BCRYPT_ROUNDS"] = "4"  # hashes rápidos en tests
os.environ["TAREAS_PERIODICAS"] = "false"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def db():
    return AsyncMongoMockClient(tz_aware=True)["parkingpro_test"]


@pytest_asyncio.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    # ASGITransport no ejecuta el lifespan, así que no se conecta a Atlas.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
