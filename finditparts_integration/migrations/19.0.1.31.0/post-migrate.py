"""Migracion 19.0.1.31.0

Cambia las reglas de precio por peso de los metodos aereos de Panama para usar
limite inferior (peso >= 0) en lugar de limite superior (peso <= 999999).
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_SERVICES = ["ground", "rapido", "flash"]


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    Carrier = env["delivery.carrier"].sudo()
    Rule = env["delivery.price.rule"].sudo()

    updated = 0
    for service in _SERVICES:
        carrier = Carrier.with_context(active_test=False).search(
            [("panama_service_type", "=", service)], limit=1
        )
        if not carrier:
            continue
        rules = Rule.with_context(active_test=False).search([
            ("carrier_id", "=", carrier.id),
            ("variable", "=", "weight"),
            ("variable_factor", "=", "weight"),
        ])
        for rule in rules:
            rule.write({"operator": ">=", "max_value": 0})
            updated += 1

    _logger.info(
        "finditparts_integration 19.0.1.31.0: %s reglas de precio actualizadas "
        "a limite inferior (peso >= 0).",
        updated,
    )
