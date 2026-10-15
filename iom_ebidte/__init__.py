from . import models
from . import controllers


# Defaults de los parametros de sistema.
#
# Esto NO se siembra con un XML de datos a proposito. Un `<record model=
# "ir.config_parameter">` hace INSERT, y `key` tiene indice unico: si el
# cliente ya habia configurado `iom_url` a mano (tipico cuando alguien
# prueba la integracion antes de instalar el modulo) el INSERT choca con
# `ir_config_parameter_key_uniq` y la instalacion se cae entera.
#
# El hook de abajo es idempotente y nunca pisa un valor existente.
PARAMETROS_POR_DEFECTO = {
    'iom_url': '',
    'iom_api_key': '',
    'iom_sucursal': '0001',
    'iom_punto_fiscal': '001',
    'iom_tipo_documento': '01',
    'iom_tipo_contribuyente': '2',
    'iom_tipo_cliente': '',
    'iom_unidad_medida_defecto': 'UND',
    'iom_codigo_ubicacion': '1-1-1',
    'iom_corregimiento': '',
    'iom_timezone_offset': '-05:00',
    'iom_timeout': '60',
    'iom_total_isc': '0.00',
}


def post_init_hook(env):
    """Crea los parametros que falten, sin tocar los que ya existan."""
    parametros = env['ir.config_parameter'].sudo()
    for clave, valor in PARAMETROS_POR_DEFECTO.items():
        # `get_param` devuelve `default` (False) cuando no existe o cuando
        # el valor guardado es cadena vacia. En ambos casos no hay nada que
        # preservar, asi que set_param es seguro.
        if parametros.get_param(clave) is False:
            parametros.set_param(clave, valor)