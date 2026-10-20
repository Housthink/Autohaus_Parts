from odoo import http
from odoo.http import request


class BestSellersController(http.Controller):

    @http.route('/best-sellers', type='http', auth='public', website=True, sitemap=True)
    def best_sellers_page(self, **kwargs):
        products = request.env['product.template'].sudo().search([
            ('best_seller', '=', True),
            ('is_published', '=', True),
            ('sale_ok', '=', True),
        ], order='name asc', limit=100)
        return request.render('finditparts_integration.best_sellers_page', {
            'products': products,
            'additional_title': 'Best Sellers',
        })
