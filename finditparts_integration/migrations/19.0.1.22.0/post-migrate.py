"""Migracion 19.0.1.22.0

Pobla los productos alternativos (relacionados) del website. Usa la heuristica
de _link_alternative_products: productos publicados de la misma marca (tag) y,
si no hay, de la misma categoria.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    products = env['finditparts.product'].sudo().search([
        ('odoo_product_id', '!=', False),
    ])

    linked = 0
    for record in products:
        before = len(record.odoo_product_id.alternative_product_ids)
        record._link_alternative_products()
        after = len(record.odoo_product_id.alternative_product_ids)
        if after > before:
            linked += 1

    _logger.info(
        'finditparts_integration 19.0.1.22.0: %s productos con alternativas '
        'vinculadas.', linked
    )
