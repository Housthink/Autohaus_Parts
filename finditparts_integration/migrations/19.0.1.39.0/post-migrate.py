"""Migracion 19.0.1.39.0

Ajusta el tamaño de fuente del texto principal de las plantillas de venta
(cotizacion, proforma, confirmacion de orden y pago realizado) de 13px a 16px
para mejorar la legibilidad del correo.

Las plantillas pertenecen al modulo ``sale`` y estan marcadas como
``noupdate=1``, por lo que no se actualizan con el upgrade de datos; se hace
por aca para las bases existentes (para instalaciones nuevas se refleja en el
body_html de la plantilla, no en este script).
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_TEMPLATE_XMLIDS = [
    "sale.email_template_edi_sale",
    "sale.email_template_proforma",
    "sale.mail_template_sale_confirmation",
    "sale.mail_template_sale_payment_executed",
]

_OLD = "font-size: 13px"
_NEW = "font-size: 16px"


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    langs = env["res.lang"].search([]).mapped("code")
    updated = 0

    for xmlid in _TEMPLATE_XMLIDS:
        template = env.ref(xmlid, raise_if_not_found=False)
        if not template:
            continue
        for lang in langs:
            template_lang = template.with_context(lang=lang)
            body = template_lang.body_html
            if body and _OLD in body:
                template_lang.write({"body_html": body.replace(_OLD, _NEW)})
                updated += 1

    _logger.info(
        "finditparts_integration 19.0.1.39.0: %s traducciones de plantillas de "
        "venta pasaron el texto principal a 16px.",
        updated,
    )
