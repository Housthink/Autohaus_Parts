"""Migracion 19.0.1.18.0

Regenera el HTML guardado de la descripcion de producto para que la pestana
"Especificaciones" muestre los datos clave del producto (lo que antes iba en
Quick Facts): numero de parte, fabricante, descripcion, categoria, condicion,
vendible, stock y peso.

La informacion se reconstruye a partir de los campos ya persistidos en el
modelo finditparts.product. El campo "condicion" no se guarda, por lo que se
omite hasta la proxima sincronizacion con la API.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

LBS_PER_KG = 0.453592


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    products = env['finditparts.product'].sudo().search([])

    changed = 0
    for record in products:
        category_label = record.category_id.name if record.category_id else ''

        weight_lbs = ''
        if record.weight:
            try:
                weight_lbs = round(float(record.weight) / LBS_PER_KG, 2)
            except (TypeError, ValueError):
                weight_lbs = ''

        product_data = {
            'part_number': record.part_number or record.sku or '',
            'sku': record.sku or '',
            'manufacturer': record.manufacturer or record.brand or '',
            'short_description': record.description or '',
            'long_description': record.description or '',
            'condition': '',
            'sellable': bool(record.sellable),
            'weight': weight_lbs,
            'current_variant': {'quantity': record.stock_quantity},
            'breadcrumbs_ancestors': [{'name': category_label}] if category_label else [],
            'pies_data': {},
        }

        new_html = record._build_html_description(product_data, [])
        if new_html and new_html != (record.long_description or ''):
            record.write({'long_description': new_html})
            if record.odoo_product_id:
                record.odoo_product_id.sudo().write({'website_description': new_html})
            changed += 1

    _logger.info(
        'finditparts_integration 19.0.1.18.0: %s descripciones regeneradas '
        'con Quick Facts en Especificaciones.', changed
    )
