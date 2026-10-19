from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    finditparts_stock = fields.Float(
        string='FinditParts Stock',
        compute='_compute_finditparts_stock',
        help='Stock quantity from FinditParts API'
    )
    
    finditparts_has_stock = fields.Boolean(
        string='Has Stock (Any Source)',
        compute='_compute_finditparts_stock',
        help='True if product has stock in Odoo OR in FinditParts'
    )
    
    @api.depends('default_code', 'qty_available')
    def _compute_finditparts_stock(self):
        """Compute stock from finditparts.product and check both sources"""
        for product in self:
            # Buscar el producto de FindinParts vinculado
            finditparts_product = self.env['finditparts.product'].sudo().search([
                ('odoo_product_id', '=', product.id)
            ], limit=1)

            # qty_available dispara el calculo de existencias de 'stock', que lee
            # stock.warehouse (sin acceso para el usuario publico del website).
            # Se lee con sudo para no romper la ficha de producto.
            qty_available = product.sudo().qty_available

            if finditparts_product:
                product.finditparts_stock = finditparts_product.stock_quantity or 0
                # Tiene stock si hay stock local O stock en FinditParts
                product.finditparts_has_stock = (qty_available > 0) or (finditparts_product.stock_quantity > 0)
            else:
                # Si no hay producto de FindinParts, usar solo stock local
                product.finditparts_stock = 0
                product.finditparts_has_stock = qty_available > 0
