"""Dónde trabaja cada persona del panel y qué puede hacer en cada parqueadero."""
from typing import FrozenSet, List, Optional

from bson import ObjectId

from app.models.enums import PERMISOS, PERMISOS_POR_ROL
from app.repositories.base import Document


def accesos(empleado: Document) -> List[Document]:
    """Los accesos del empleado. Un empleado sin migrar conserva su parqueadero único."""
    if "accesos" in empleado:
        return empleado["accesos"]
    if empleado.get("parqueadero_id") is not None:
        permisos = sorted(PERMISOS) if empleado["rol"] == "administrador" else []
        return [{"parqueadero_id": empleado["parqueadero_id"], "permisos": permisos}]
    return []


def parqueaderos_de(empleado: Document) -> List[ObjectId]:
    return [a["parqueadero_id"] for a in accesos(empleado)]


def permisos_en(empleado: Document, parqueadero_id: ObjectId) -> Optional[FrozenSet[str]]:
    """None si no trabaja en ese parqueadero."""
    for acceso in accesos(empleado):
        if acceso["parqueadero_id"] == parqueadero_id:
            if empleado["rol"] == "administrador":
                return frozenset(acceso["permisos"])
            return PERMISOS_POR_ROL[empleado["rol"]]
    return None
