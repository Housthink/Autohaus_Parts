"""Migracion 19.0.1.36.0

Aplica el layout de correo con identidad AutoHaus Parts
(``finditparts_integration.autohaus_mail_layout``) a las plantillas de venta
(cotizacion, proforma, confirmacion de orden y pago realizado).

Estas plantillas pertenecen al modulo ``sale`` y estan marcadas como
``noupdate=1``, por lo que Odoo no las actualiza durante el upgrade de datos.
Por eso se fija ``email_layout_xmlid`` por aca para las bases ya existentes;
en instalaciones nuevas lo hace el archivo data/mail_templates_autohaus.xml.
"""

import logging

import odoo

_logger = logging.getLogger(__name__)

_LAYOUT_XMLID = "finditparts_integration.autohaus_mail_layout"

_TEMPLATE_XMLIDS = [
    "sale.email_template_edi_sale",
    "sale.email_template_proforma",
    "sale.mail_template_sale_confirmation",
    "sale.mail_template_sale_payment_executed",
]


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    updated = 0
    for xmlid in _TEMPLATE_XMLIDS:
        template = env.ref(xmlid, raise_if_not_found=False)
        if not template:
            continue
        if template.email_layout_xmlid != _LAYOUT_XMLID:
            template.write({"email_layout_xmlid": _LAYOUT_XMLID})
            updated += 1

    _logger.info(
        "finditparts_integration 19.0.1.36.0: %s plantillas de venta pasaron "
        "al layout de correo AutoHaus Parts.",
        updated,
    )
