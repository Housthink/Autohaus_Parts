"""Migracion 19.0.1.30.0

Crea las reglas de precio por peso (US$2.50 por libra facturable) para los
metodos de envio aereos de Panama. La tarifa base de FinditParts se toma como 0
hasta que la API la devuelva.

Precio = 0 + 2.50 * peso (en lb, redondeado hacia arriba por el motor).
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_RULES = [
    ("ground", "carrier_panama_ground"),
    ("rapido", "carrier_panama_rapido"),
    ("flash", "carrier_panama_flash"),
]


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    Carrier = env["delivery.carrier"].sudo()
    Rule = env["delivery.price.rule"].sudo()

    created = 0
    for service, _xmlid in _RULES:
        carrier = Carrier.with_context(active_test=False).search(
            [("panama_service_type", "=", service)], limit=1
        )
        if not carrier:
            continue
        existing = Rule.with_context(active_test=False).search([
            ("carrier_id", "=", carrier.id),
            ("variable", "=", "weight"),
            ("variable_factor", "=", "weight"),
        ])
        if existing:
            continue
        Rule.create({
            "carrier_id": carrier.id,
            "sequence": 10,
            "variable": "weight",
            "operator": ">=",
            "max_value": 0,
            "list_base_price": 0.0,
            "list_price": 2.50,
            "variable_factor": "weight",
        })
        created += 1

    _logger.info(
        "finditparts_integration 19.0.1.30.0: %s reglas de precio por peso "
        "creadas para los metodos aereos de Panama.",
        created,
    )
