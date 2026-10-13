from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class FindinPartOrder(models.Model):
    _name = 'finditparts.order'
    _description = 'FindinPart Order'
    _rec_name = 'reference'
    _order = 'create_date desc'

    reference = fields.Char('Order Reference', required=True, index=True)
    finditparts_order_id = fields.Char('FindinPart Order ID', index=True)
    
    order_date = fields.Datetime('Order Date', required=True, default=fields.Datetime.now)
    customer_id = fields.Many2one('res.partner', 'Customer', required=True)
    order_lines = fields.One2many('finditparts.order.line', 'order_id', 'Order Lines')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], string='Status', default='draft')
    
    total_amount = fields.Monetary('Total Amount', currency_field='currency_id', compute='_compute_total')
    currency_id = fields.Many2one('res.currency', 'Currency', default=lambda self: self.env.company.currency_id)
    
    shipping_address = fields.Text('Shipping Address')
    tracking_number = fields.Char('Tracking Number')
    estimated_delivery = fields.Date('Estimated Delivery')
    
    odoo_sale_order_id = fields.Many2one('sale.order', 'Odoo Sale Order', ondelete='set null')
    sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('failed', 'Failed'),
    ], string='Sync Status', default='pending')
    last_sync_date = fields.Datetime('Last Sync Date')
    sync_errors = fields.Text('Sync Errors')
    
    notes = fields.Text('Notes')
    active = fields.Boolean('Active', default=True)
    create_date = fields.Datetime('Created Date', readonly=True)
    write_date = fields.Datetime('Last Updated', readonly=True)
    
    @api.depends('order_lines.subtotal')
    def _compute_total(self):
        for order in self:
            order.total_amount = sum(line.subtotal for line in order.order_lines)
    
    @api.constrains('order_lines')
    def _check_order_lines(self):
        for order in self:
            if not order.order_lines:
                raise ValidationError(_('Order must have at least one line'))
    
    def action_confirm(self):
        """Confirm the order"""
        self.ensure_one()
        if self.state == 'draft':
            self.state = 'confirmed'
            self._create_odoo_sale_order()
    
    def action_process(self):
        """Process the order"""
        self.ensure_one()
        if self.state == 'confirmed':
            self.state = 'processing'
    
    def action_ship(self):
        """Mark order as shipped"""
        self.ensure_one()
        if self.state == 'processing':
            self.state = 'shipped'
    
    def action_deliver(self):
        """Mark order as delivered"""
        self.ensure_one()
        if self.state == 'shipped':
            self.state = 'delivered'
    
    def action_cancel(self):
        """Cancel the order"""
        self.ensure_one()
        if self.state in ['draft', 'confirmed']:
            self.state = 'cancelled'
            if self.odoo_sale_order_id:
                self.odoo_sale_order_id.action_cancel()
    
    def _create_odoo_sale_order(self):
        """Create corresponding Odoo sale order"""
        self.ensure_one()
        try:
            order_lines = []
            for line in self.order_lines:
                if line.product_id:
                    order_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.description,
                        'product_uom_qty': line.quantity,
                        'price_unit': line.unit_price,
                        'product_uom': line.product_id.uom_id.id,
                    }))
            
            sale_order_vals = {
                'partner_id': self.customer_id.id,
                'date_order': self.order_date,
                'order_line': order_lines,
                'note': f"FindinPart Order: {self.reference}",
            }
            
            sale_order = self.env['sale.order'].create(sale_order_vals)
            self.odoo_sale_order_id = sale_order.id
            self.sync_status = 'synced'
            self.last_sync_date = fields.Datetime.now()
            
            return sale_order
            
        except Exception as e:
            _logger.error(f"Failed to create Odoo sale order: {str(e)}")
            self.sync_status = 'failed'
            self.sync_errors = str(e)
            return False
    
    def action_view_odoo_order(self):
        """Open the related Odoo sale order"""
        self.ensure_one()
        if self.odoo_sale_order_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.odoo_sale_order_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False


class FindinPartOrderLine(models.Model):
    _name = 'finditparts.order.line'
    _description = 'FindinPart Order Line'
    _rec_name = 'product_id'

    order_id = fields.Many2one('finditparts.order', 'Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.template', 'Product', required=True)
    finditparts_product_id = fields.Many2one('finditparts.product', 'FindinPart Product')
    
    description = fields.Char('Description', required=True)
    quantity = fields.Float('Quantity', required=True, default=1.0)
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id', required=True)
    subtotal = fields.Monetary('Subtotal', currency_field='currency_id', compute='_compute_subtotal', store=True)
    
    currency_id = fields.Many2one('res.currency', 'Currency', related='order_id.currency_id', store=True)
    
    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
    
    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Quantity must be greater than zero'))
