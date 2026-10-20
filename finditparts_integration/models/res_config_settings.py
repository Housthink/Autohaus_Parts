from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    finditparts_whatsapp_url = fields.Char(
        string='Enlace de WhatsApp',
        config_parameter='finditparts_integration.whatsapp_url',
        default='https://wa.link/1ru5s3',
        help='Enlace al que lleva el botón flotante. '
             'Si se deja vacío, el botón no se muestra.',
    )
