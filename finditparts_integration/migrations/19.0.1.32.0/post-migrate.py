"""Migracion 19.0.1.32.0

Marca como visibles para clientes (visible_to_customers=True) todos los tags de
marca (product.tag) que tengan productos asociados, para que las marcas
aparezcan en el home y en el glosario de marcas del website.

Historicamente _ensure_brand_tag() creaba los tags sin fijar
visible_to_customers, dejandolos invisibles por defecto en algunos entornos.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    Tag = env["product.tag"].sudo()
    tags = Tag.search([("product_template_ids", "!=", False)])
    invisible = tags.filtered(lambda t: not t.visible_to_customers)
    if invisible:
        invisible.write({"visible_to_customers": True})

    _logger.info(
        "finditparts_integration 19.0.1.32.0: %s tags de marca marcados como "
        "visibles para clientes.",
        len(invisible),
    )
