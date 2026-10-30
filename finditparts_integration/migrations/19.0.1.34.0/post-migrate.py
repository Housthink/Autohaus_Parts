"""Migracion 19.0.1.34.0

Actualiza el multiplicador por libra de los metodos aereos de Panama de 2.50 a
3.75 en las reglas de precio por peso, en el ir.config_parameter y en el markup
de la configuracion activa.

A partir de esta version la tarifa de envio domestico dentro de Estados Unidos
reportada por FinditParts (flujo de carrito /shipping_methods) se usa como base
de la cotizacion de Panama; el markup por libra se suma encima de esa base. La
base se cachea en sale.order (logistics_usa_base_rate) y se invalida cuando
cambia el contenido del carrito o el almacen de recogida.

El campo nuevo ``finditparts.product.variant_id`` se rellena automaticamente en
la proxima sincronizacion de cada producto. Los productos ya sincronizados caen
al fallback ``variant_id = finditparts_id`` hasta que se vuelvan a sincronizar.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_SERVICES = ["ground", "rapido", "flash"]
_OLD_MARKUP = 2.50
_NEW_MARKUP = 3.75


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
            if abs(rule.list_price - _OLD_MARKUP) < 0.0001:
                rule.write({"list_price": _NEW_MARKUP})
                updated += 1

    env["ir.config_parameter"].sudo().set_param(
        "autohaus_shipping.markup_per_lb", str(_NEW_MARKUP)
    )

    config = env["finditparts.config"].sudo().search([], limit=1)
    if config and abs(config.panama_markup_per_lb - _OLD_MARKUP) < 0.0001:
        config.panama_markup_per_lb = _NEW_MARKUP

    _logger.info(
        "finditparts_integration 19.0.1.34.0: %s reglas de precio actualizadas "
        "a %s USD/lb.",
        updated,
        _NEW_MARKUP,
    )
