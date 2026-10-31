from typing import Dict, FrozenSet, Literal

EstadoParqueadero = Literal["activo", "suspendido", "en_prueba"]
EstadoSede = Literal["activa", "inactiva", "mantenimiento"]
RolEmpleado = Literal["administrador", "operador", "cajero"]
EstadoEmpleado = Literal["activo", "inactivo"]
EstadoSocio = Literal["activo", "inactivo"]
TipoEspacio = Literal["carro", "moto", "discapacitado"]
EstadoEspacio = Literal["disponible", "ocupado", "mantenimiento"]
TipoVehiculo = Literal["carro", "moto"]
EstadoReserva = Literal["pendiente", "confirmada", "cancelada", "completada"]
EstadoSesion = Literal["activa", "finalizada"]
MetodoPago = Literal["efectivo", "tarjeta", "app"]
EstadoPago = Literal["pendiente", "pagado", "rechazado", "reembolsado"]
# Estado de una plaza para un horario concreto (calculado, no se guarda)
EstadoPlaza = Literal["disponible", "ocupada", "reservada", "mantenimiento"]

# Un espacio para discapacitados se cobra con tarifa de carro.
TARIFA_POR_TIPO_ESPACIO = {"carro": "carro", "moto": "moto", "discapacitado": "carro"}

EstadoSuscripcion = Literal["activa", "cancelada", "vencida"]
PlanUsuario = Literal["por_uso", "afiliado"]
TipoActividad = Literal[
    "reserva_creada", "reserva_confirmada", "reserva_cancelada", "reserva_vencida",
    "check_in", "check_out", "pago", "reembolso", "espacio_estado",
]

# Permisos de un administrador en cada parqueadero. El socio siempre los tiene todos.
Permiso = Literal[
    "ver_operacion", "cobrar_caja", "hacer_reembolsos", "gestionar_tarifas",
    "gestionar_sedes", "gestionar_empleados", "ver_metricas", "editar_configuracion",
]
PERMISOS: FrozenSet[str] = frozenset(Permiso.__args__)  # type: ignore[attr-defined]
# Operador y cajero tienen roles fijos: conservan lo que ya podían hacer.
PERMISOS_POR_ROL: Dict[str, FrozenSet[str]] = {
    "operador": frozenset({"ver_operacion", "cobrar_caja", "ver_metricas"}),
    "cajero": frozenset({"ver_operacion", "cobrar_caja", "ver_metricas", "hacer_reembolsos"}),
}

AccionAuditoria = Literal["crear", "actualizar", "eliminar", "dar_acceso", "quitar_acceso"]
