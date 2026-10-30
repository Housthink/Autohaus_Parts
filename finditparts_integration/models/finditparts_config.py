from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class FindinPartConfig(models.Model):
    _name = 'finditparts.config'
    _description = 'FindinPart API Configuration'
    _rec_name = 'name'

    name = fields.Char('Configuration Name', required=True, default='Default')
    active = fields.Boolean('Active', default=True)
    
    api_base_url = fields.Char('API Base URL', required=True,
                              default='https://www-build.finditparts.com')
    
    # JWT Authentication (FindinPart uses signed tokens)
    jwt_issuer = fields.Char('JWT Issuer (iss)', required=True,
                            default='autohaus-build',
                            help='Your assigned issuer identifier from FindinPart')
    jwt_secret = fields.Char('JWT Secret Key', required=True,
                            default='222b6c16-b54a-4ad6-a2c7-e43ba7c23060',
                            help='Secret key for signing JWT tokens')
    jwt_audience = fields.Char('JWT Audience (aud)', required=True,
                              default='https://api.finditparts.com',
                              help='API endpoint audience for JWT')
    jwt_expiry_hours = fields.Integer('JWT Token Expiry (Hours)', default=1,
                                     help='How long JWT tokens remain valid')
    
    sync_interval_hours = fields.Integer('Sync Interval (Hours)', default=6)
    last_sync_date = fields.Datetime('Last Sync Date', readonly=True)
    next_sync_date = fields.Datetime('Next Sync Date', readonly=True)
    
    default_category_id = fields.Many2one('product.category', 'Default Category')
    default_warehouse_id = fields.Many2one('stock.warehouse', 'Default Warehouse')
    auto_create_products = fields.Boolean('Auto Create Products', default=True)
    auto_update_prices = fields.Boolean('Auto Update Prices', default=True)
    auto_update_stock = fields.Boolean('Auto Update Stock', default=True)
    auto_publish_website = fields.Boolean('Auto Publish on Website', default=True,
                                         help='Automatically publish synced products on the eCommerce website')
    
    # Contact Information for Out-of-Stock Requests
    contact_email = fields.Char('Contact Email', required=True, default='tmjhosep@gmail.com',
                                help='Email address to receive product availability requests')
    
    # Pricing Configuration
    price_margin_percent = fields.Float('Price Margin (%)', default=10.0,
                                       help='Percentage to add to FinditParts prices when creating products in Odoo (e.g., 10 for 10%)')

    # Discount via Pricelist
    apply_discount_as_pricelist = fields.Boolean(
        'Apply Discount via Pricelist', default=False,
        help='When enabled, the discount reported by FinditParts is applied through '
             'a website pricelist so Odoo natively shows the original price with a '
             'strikethrough and the discount percentage on the eCommerce.',
    )
    discount_pricelist_id = fields.Many2one(
        'product.pricelist', 'Discount Pricelist',
        help='Pricelist used to apply the discount. Leave empty to automatically '
             'find or create a selectable pricelist for the website.',
    )
    
    # Shipping Addresses
    shipping_address_usa = fields.Text('Shipping Address (USA)', default='Address example #123',
                                       help='Shipping address in the United States')
    shipping_address_panama = fields.Text('Shipping Address (Panama)', default='Address example #123',
                                          help='Shipping address in Panama')

    # Panama shipping commercial markup and service toggles. These are the only
    # figures that may be hardcoded/configurable; the base rate always comes
    # from the FinditParts API.
    panama_markup_per_lb = fields.Float(
        'Panama Air Markup (USD/lb)', default=3.75,
        help='Commercial markup applied per billable pound on top of the '
             'FinditParts base rate for Panama air services (Ground, Rápido, '
             'Flash). Internal only; never shown to the customer.')
    enable_shipping_ground = fields.Boolean('Enable Ground', default=True)
    enable_shipping_rapido = fields.Boolean('Enable Rápido', default=True)
    enable_shipping_flash = fields.Boolean('Enable Flash', default=True)
    enable_shipping_lcl = fields.Boolean(
        'Enable Marítimo LCL', default=False,
        help='LCL is quoted manually because the FinditParts API does not '
             'provide product dimensions, so there is no billable volume.')
    

    auto_confirm_orders = fields.Boolean('Auto Confirm Orders', default=False)
    default_payment_term_id = fields.Many2one('account.payment.term', 'Default Payment Term')
    
    enable_debug_logging = fields.Boolean('Enable Debug Logging', default=False)
    max_log_entries = fields.Integer('Max Log Entries', default=1000)
    
    @api.constrains('api_base_url')
    def _check_api_url(self):
        for record in self:
            if record.api_base_url and not record.api_base_url.startswith(('http://', 'https://')):
                raise ValidationError(_('API Base URL must start with http:// or https://'))
    
    @api.constrains('sync_interval_hours')
    def _check_sync_interval(self):
        for record in self:
            if record.sync_interval_hours < 1:
                raise ValidationError(_('Sync interval must be at least 1 hour'))
    
    def test_api_connection(self):
        """Test the API connection with current credentials"""
        self.ensure_one()
        try:
            from ..utils.api_client import FindinPartAPIClient
            
            client = FindinPartAPIClient(self)
            result = client.test_connection()
            
            if result.get('success'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('API connection successful!'),
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': result.get('error', _('API connection failed')),
                        'type': 'danger',
                    }
                }
        except Exception as e:
            _logger.error(f"API connection test failed: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def get_active_config(self):
        """Get the active configuration"""
        return self.search([('active', '=', True)], limit=1)
    
    def update_sync_schedule(self):
        """Update the next sync date based on interval"""
        for record in self:
            if record.sync_interval_hours and record.last_sync_date:
                from datetime import timedelta
                record.next_sync_date = record.last_sync_date + timedelta(hours=record.sync_interval_hours)
