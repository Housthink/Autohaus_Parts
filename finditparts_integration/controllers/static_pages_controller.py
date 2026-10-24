from odoo import http
from odoo.http import request


class AutohausStaticPages(http.Controller):
    """Public informational pages linked from the Autohaus footer."""

    @staticmethod
    def _render(template):
        return request.render(f'finditparts_integration.{template}', {})

    @http.route('/cores', type='http', auth='public', website=True, sitemap=True)
    def cores(self, **kwargs):
        return self._render('cores_page')

    @http.route('/envios', type='http', auth='public', website=True, sitemap=True)
    def shipping(self, **kwargs):
        return self._render('shipping_page')

    @http.route('/directorio-repuestos', type='http', auth='public', website=True, sitemap=True)
    def parts_directory(self, **kwargs):
        return self._render('parts_directory_page')

    @http.route('/nosotros', type='http', auth='public', website=True, sitemap=True)
    def about(self, **kwargs):
        return self._render('about_page')

    @http.route('/blog', type='http', auth='public', website=True, sitemap=True)
    def blog(self, **kwargs):
        return self._render('blog_page')

    @http.route('/faq', type='http', auth='public', website=True, sitemap=True)
    def faq(self, **kwargs):
        return self._render('faq_page')

    @http.route('/terminos-de-uso', type='http', auth='public', website=True, sitemap=True)
    def terms(self, **kwargs):
        return self._render('terms_page')

    @http.route('/politica-de-privacidad', type='http', auth='public', website=True, sitemap=True)
    def privacy(self, **kwargs):
        return self._render('privacy_page')
