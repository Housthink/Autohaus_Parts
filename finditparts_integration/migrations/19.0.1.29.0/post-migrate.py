"""Migracion 19.0.1.29.0

Actualiza los metodos de envio de Panama para que sean reglas por peso
(base_on_rule) en lugar de precio fijo.

Precio = base API (0 mientras FinditParts no la devuelve) + US$2.50 por libra
facturable (peso redondeado hacia arriba). Se quitan los country_ids porque el
destino lo determina la seleccion de almacen en el checkout (no el pais del
partner).
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


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    Carrier = env["delivery.carrier"].sudo()
    delivery_product = env.ref("delivery.product_product_delivery", raise_if_not_found=False)

    created = 0
    updated = 0
    for service, name, sequence, active in _SERVICES:
        carrier = Carrier.with_context(active_test=False).search(
            [("panama_service_type", "=", service)], limit=1
        )
        if carrier:
            write_vals = {
                "delivery_type": "base_on_rule",
                "sequence": sequence,
                "weight_unit": "lb",
                "is_published": True,
                "active": active,
                "country_ids": [(5, 0, 0)],
            }
            if delivery_product:
                write_vals["product_id"] = delivery_product.id
            carrier.write(write_vals)
            updated += 1
            continue

        values = {
            "name": name,
            "delivery_type": "base_on_rule",
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

    _logger.info(
        "finditparts_integration 19.0.1.29.0: %s metodos de envio de Panama "
        "creados y %s actualizados a base_on_rule.",
        created,
        updated,
    )
