"""Migracion 19.0.1.21.0

Regenera el HTML guardado de la descripcion de producto para:
- Pestaña "Especificaciones": muestra specs técnicas (attribute_pairs) en vez de Quick Facts
- Pestaña "Ficha técnica": muestra Quick Facts (datos clave del producto)
- Pestaña "Compatibilidad": referencias equivalentes como enlaces clicables
- Pestaña "Entrega e información de envío": tiempos de entrega y envío
"""

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
        # Reconstruir product_data desde los campos almacenados
        category_label = record.category_id.name if record.category_id else ''
        
        # Obtener attribute_pairs desde el campo specifications
        attribute_pairs = []
        if record.specifications:
            for line in record.specifications.splitlines():
                line = line.strip()
                if ':' in line:
                    name, value = line.split(':', 1)
                    if name.strip() and value.strip():
                        attribute_pairs.append((name.strip(), value.strip()))
        
        product_data = {
            'part_number': record.part_number or record.sku or '',
            'sku': record.sku or '',
            'manufacturer': record.manufacturer or record.brand or '',
            'short_description': record.description or '',
            'long_description': record.description or '',
            'description': record.description or '',
            'condition': '',
            'sellable': bool(record.sellable),
            'weight': record.weight,
            'stock_quantity': record.stock_quantity,
            'current_variant': {'quantity': record.stock_quantity},
            'breadcrumbs_ancestors': [{'name': category_label}] if category_label else [],
            'pies_data': {},
            'purchase_notes': [],
        }

        new_html = record._build_html_description(product_data, attribute_pairs)
        if new_html and new_html != (record.long_description or ''):
            record.write({'long_description': new_html})
            if record.odoo_product_id:
                record.odoo_product_id.sudo().write({'website_description': new_html})
            changed += 1

    _logger.info(
        'finditparts_integration 19.0.1.21.0: %s descripciones regeneradas '
        'con especificaciones técnicas, ficha técnica, compatibilidad y envío.', changed
    )
