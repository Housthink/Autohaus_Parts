"""Migracion 19.0.1.27.0

Regenera el HTML guardado de la descripcion de producto para quitar el enlace
"Ver página del fabricante" de la pestana "Informacion del fabricante".
"""

import json
import logging

import odoo

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    products = env['finditparts.product'].sudo().search([])

    changed = 0
    for record in products:
        pies_data = {}
        if record.pies_data_json:
            try:
                pies_data = json.loads(record.pies_data_json)
            except (ValueError, TypeError):
                pies_data = {}

        attribute_pairs = []
        if record.specifications:
            for line in record.specifications.splitlines():
                line = line.strip()
                if ':' in line:
                    name, value = line.split(':', 1)
                    if name.strip() and value.strip():
                        attribute_pairs.append((name.strip(), value.strip()))

        category_label = record.category_id.name if record.category_id else ''

        product_data = {
            'part_number': record.part_number or record.sku or '',
            'sku': record.sku or '',
            'manufacturer': record.manufacturer or record.brand or '',
            'brand': record.brand or '',
            'manufacturer_image': record.manufacturer_image or '',
            'product_url': record.product_url or '',
            'short_description': record.description or '',
            'long_description': record.description or '',
            'description': record.description or '',
            'condition': '',
            'sellable': bool(record.sellable),
            'weight': record.weight,
            'stock_quantity': record.stock_quantity,
            'current_variant': {'quantity': record.stock_quantity},
            'breadcrumbs_ancestors': [{'name': category_label}] if category_label else [],
            'pies_data': pies_data,
            'purchase_notes': [],
        }

        new_html = record._build_html_description(product_data, attribute_pairs)
        if new_html and new_html != (record.long_description or ''):
            record.write({'long_description': new_html})
            if record.odoo_product_id:
                record.odoo_product_id.sudo().write({'website_description': new_html})
            changed += 1

    _logger.info(
        'finditparts_integration 19.0.1.27.0: %s descripciones regeneradas '
        'sin el enlace "Ver página del fabricante".', changed
    )
