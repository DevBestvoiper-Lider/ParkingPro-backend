from typing import Any, Dict, Optional

from bson import ObjectId

from app.core.utils import utcnow
from app.models.collections import AUDITORIA
from app.repositories.base import BaseRepository, Document

CAMPOS_PRIVADOS = {"password_hash", "reset_token_hash", "reset_expira", "sesion_version"}


class AuditoriaRepository(BaseRepository):
    """Historial permanente: quién cambió qué, cuándo, y los valores anteriores y nuevos."""

    collection_name = AUDITORIA

    async def registrar(
        self,
        actor: Document,
        accion: str,
        entidad: str,
        entidad_id: ObjectId,
        parqueadero_id: Optional[ObjectId] = None,
        antes: Optional[Document] = None,
        despues: Optional[Document] = None,
    ) -> Document:
        doc: Dict[str, Any] = {
            "fecha": utcnow(),
            "actor": {"tipo": actor.get("cuenta", "sistema"), "id": actor.get("_id"), "nombre": actor.get("nombre", "")},
            "accion": accion,
            "entidad": entidad,
            "entidad_id": entidad_id,
        }
        if parqueadero_id is not None:
            doc["parqueadero_id"] = parqueadero_id
        if antes is not None:
            doc["antes"] = _sin_privados(antes)
        if despues is not None:
            doc["despues"] = _sin_privados(despues)
        return await self.insert(doc)


def cambios_de(anterior: Document, cambios: Document) -> Dict[str, Document]:
    """Solo los campos que cambian: {"antes": {...}, "despues": {...}}."""
    distintos = {k: v for k, v in cambios.items() if anterior.get(k) != v}
    return {
        "antes": {k: anterior.get(k) for k in distintos},
        "despues": distintos,
    }


def _sin_privados(doc: Document) -> Document:
    return {k: v for k, v in doc.items() if k not in CAMPOS_PRIVADOS}
