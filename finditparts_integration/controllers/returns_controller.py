from odoo import http
from odoo.http import request


class ReturnsController(http.Controller):

    @http.route('/devoluciones', type='http', auth='public', website=True, sitemap=True)
    def returns_page(self, **kwargs):
        return request.render('finditparts_integration.returns_page', {})
