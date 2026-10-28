"""Migracion 19.0.1.28.0

Crea los metodos de envio de Panama (Ground, Rapido, Flash, LCL) y los
parametros de configuracion de recargos para el motor de cotizacion Autohaus.

Estos registros se definen tambien en data/shipping_data.xml; aqui se crean
idempotentemente por si el modulo ya estaba instalado (data con noupdate=1 no
se vuelve a aplicar sobre instalaciones existentes).
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_SERVICES = [
    ("ground", "Ground · aéreo (Panamá)", 10, True),
    ("rapido", "Rápido · aéreo (Panamá)", 20, True),
    ("flash", "Flash · aéreo (Panamá)", 30, True),
    ("lcl", "Marítimo · LCL (Panamá)", 40, False),
]

_PARAMS = [
    ("autohaus_shipping.markup_per_lb", "2.50"),
    ("autohaus_shipping.enable_panama_ground", "True"),
    ("autohaus_shipping.enable_panama_rapido", "True"),
    ("autohaus_shipping.enable_panama_flash", "True"),
    ("autohaus_shipping.enable_panama_lcl", "False"),
]


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    Carrier = env["delivery.carrier"].sudo()
    delivery_product = env.ref("delivery.product_product_delivery", raise_if_not_found=False)

    created = 0
    for service, name, sequence, active in _SERVICES:
        carrier = Carrier.with_context(active_test=False).search(
            [("panama_service_type", "=", service)], limit=1
        )
        if carrier:
            continue
        values = {
            "name": name,
            "delivery_type": "fixed",
            "fixed_price": 0.0,
            "sequence": sequence,
            "panama_service_type": service,
            "weight_unit": "lb",
            "is_published": True,
            "active": active,
        }
        if delivery_product:
            values["product_id"] = delivery_product.id
        Carrier.create(values)
        created += 1

    Param = env["ir.config_parameter"].sudo()
    for key, value in _PARAMS:
        Param.set_param(key, value)

    _logger.info(
        "finditparts_integration 19.0.1.28.0: %s metodos de envio de Panama "
        "creados y %s parametros de configuracion establecidos.",
        created,
        len(_PARAMS),
    )
