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

    def get_home_brands(self, limit=12):
        """Devuelve las marcas (product.tag) con productos publicados, ordenadas
        por cantidad de productos, para la seccion de marcas lideres del home."""
        Tag = self.env['product.tag'].sudo()
        tags = Tag.search([
            ('visible_to_customers', '=', True),
            ('product_template_ids', '!=', False),
        ])
        counted = []
        for tag in tags:
            published = tag.product_template_ids.filtered(
                lambda p: p.is_published and p.sale_ok
            )
            if published:
                counted.append((len(published), tag))
        counted.sort(key=lambda item: (-item[0], (item[1].name or '').lower()))
        return [item[1] for item in counted[:limit]]
