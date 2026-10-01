from decimal import Decimal
from typing import Annotated, Any

from bson import Decimal128, ObjectId
from pydantic import AfterValidator, AliasChoices, BaseModel, BeforeValidator, Field, PlainSerializer


def _oid_to_str(value: Any) -> Any:
    return str(value) if isinstance(value, ObjectId) else value


def _validate_oid(value: str) -> str:
    if not ObjectId.is_valid(value):
        raise ValueError("ObjectId inválido")
    return value


def _decimal128_to_decimal(value: Any) -> Any:
    return value.to_decimal() if isinstance(value, Decimal128) else value


# Salida: ObjectId de Mongo -> str
PyObjectId = Annotated[str, BeforeValidator(_oid_to_str)]
# Entrada: str que debe ser un ObjectId válido
ObjectIdStr = Annotated[str, AfterValidator(_validate_oid)]
# Dinero: Decimal128 en Mongo, número en el JSON
Money = Annotated[
    Decimal,
    BeforeValidator(_decimal128_to_decimal),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class MongoModel(BaseModel):
    """Modelo de salida para documentos de Mongo: expone `_id` como `id`."""

    id: PyObjectId = Field(validation_alias=AliasChoices("_id", "id"))
