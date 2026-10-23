"""Migracion 19.0.1.17.0

Regenera el HTML guardado de la descripcion de producto al nuevo formato de
pestanas:

  - Descripcion            (dinamico, desde el campo description)
  - Especificaciones       (dinamico, desde el campo specifications)
  - Compatibilidad         (solo se genera al re-sincronizar; no estaba guardado)
  - Garantia y Devoluciones (estatico, traducido)

El HTML anterior solo guardaba "Quick Facts" y "Product Attributes". Esta
migracion reconstruye la descripcion usando los campos ya persistidos en el
modelo (description y specifications) y llama a la misma logica de generacion
que usa la sincronizacion, para no duplicar el marcado.

Es idempotente: si el registro ya esta en el formato nuevo, el resultado de
regenerarlo es identico y el write no produce cambios.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)


def _parse_specifications(specifications):
    """Convierte el texto 'nombre: valor' (una linea por fila) en pares."""
    pairs = []
    for line in (specifications or '').splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        name, value = line.split(':', 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            pairs.append((name, value))
    return pairs


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    products = env['finditparts.product'].sudo().search([])

    changed = 0
    for record in products:
        product_data = {
            'short_description': record.description or '',
            'long_description': record.description or '',
            'manufacturer': record.manufacturer or record.brand or '',
            'part_number': record.part_number or record.sku or '',
            'pies_data': {},
        }
        attribute_pairs = _parse_specifications(record.specifications)
        new_html = record._build_html_description(product_data, attribute_pairs)

        if new_html and new_html != (record.long_description or ''):
            record.write({'long_description': new_html})
            if record.odoo_product_id:
                record.odoo_product_id.sudo().write({'website_description': new_html})
            changed += 1

    _logger.info(
        'finditparts_integration 19.0.1.17.0: %s descripciones regeneradas '
        'al formato de pestanas.', changed
    )
