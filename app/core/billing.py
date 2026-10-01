import math
from datetime import datetime
from decimal import Decimal

from app.core.utils import as_utc


def calcular_total(valor_hora: Decimal, inicio: datetime, fin: datetime) -> Decimal:
    """Cobra por hora o fracción, con un mínimo de una hora."""
    segundos = max((as_utc(fin) - as_utc(inicio)).total_seconds(), 0)
    horas = max(math.ceil(segundos / 3600), 1)
    return (valor_hora * horas).quantize(Decimal("0.01"))
