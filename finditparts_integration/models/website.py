from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def get_whatsapp_url(self):
        self.ensure_one()
        url = self.env['ir.config_parameter'].sudo().get_param(
            'finditparts_integration.whatsapp_url',
            'https://wa.link/1ru5s3',
        )
        url = (url or '').strip()
        if not url:
            return False
        if not url.lower().startswith(('http://', 'https://')):
            url = 'https://' + url
        return url
