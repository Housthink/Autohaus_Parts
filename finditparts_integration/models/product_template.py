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

    best_seller = fields.Boolean(
        string='Best Seller',
        default=False,
        help='Automatically flagged when the product appears in the FinditParts best-seller ranking.',
    )

    finditparts_discount_percent = fields.Float(
        string='FinditParts Discount (%)',
        help='Discount reported by FinditParts during the last synchronization.',
    )

    finditparts_part_number = fields.Char(
        string='FinditParts Part Number',
        compute='_compute_finditparts_part_number',
        help='Part number reported by FinditParts for the linked product.',
    )

    @api.depends('default_code')
    def _compute_finditparts_part_number(self):
        FinditPartsProduct = self.env['finditparts.product'].sudo()
        part_numbers = {}
        for finditparts_product in FinditPartsProduct.search([
            ('odoo_product_id', 'in', self.ids)
        ]):
            part_numbers.setdefault(
                finditparts_product.odoo_product_id.id,
                finditparts_product.part_number,
            )

        for product in self:
            product.finditparts_part_number = part_numbers.get(product.id) or product.default_code

    @api.depends('default_code', 'qty_available')
    def _compute_finditparts_stock(self):
        """Compute stock from finditparts.product and check both sources"""
        # Una sola consulta para todos los productos vinculados (evita N+1).
        finditparts_products = self.env['finditparts.product'].sudo().search([
            ('odoo_product_id', 'in', self.ids)
        ])
        fp_stock_by_product = {
            fp.odoo_product_id.id: fp.stock_quantity or 0
            for fp in finditparts_products
        }

        # qty_available dispara el calculo de existencias de 'stock', que lee
        # stock.warehouse (sin acceso para el usuario publico del website).
        # Se lee con sudo y de una sola vez para todo el recordset.
        local_qtys = self.sudo().mapped('qty_available')
        qty_available_by_product = dict(zip(self.ids, local_qtys))

        for product in self:
            fp_stock = fp_stock_by_product.get(product.id)
            local_qty = qty_available_by_product.get(product.id, 0)
            if fp_stock is not None:
                product.finditparts_stock = fp_stock
                # Tiene stock si hay stock local O stock en FinditParts
                product.finditparts_has_stock = (local_qty > 0) or (fp_stock > 0)
            else:
                # Si no hay producto de FindinParts, usar solo stock local
                product.finditparts_stock = 0
                product.finditparts_has_stock = local_qty > 0
