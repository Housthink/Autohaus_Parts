from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class FinditPartsProductSyncWizard(models.TransientModel):
    _name = 'finditparts.product.sync.wizard'
    _description = 'FinditParts Product Sync Wizard'

    sync_type = fields.Selection([
        ('search', 'Search Products'),
        ('part_number', 'Specific Part Number'),
        ('all', 'All Products (Limited)')
    ], string='Sync Type', default='search', required=True)
    
    search_query = fields.Char('Search Query', help='Search for products by keyword')
    part_number = fields.Char('Part Number', help='Sync specific product by part number')
    limit = fields.Integer('Limit', default=100, help='Maximum number of products to sync')
    
    auto_create_odoo_products = fields.Boolean('Create Odoo Products', default=True,
                                               help='Automatically create products in Odoo catalog')
    
    # Results fields
    sync_completed = fields.Boolean('Sync Completed', default=False, readonly=True)
    created_count = fields.Integer('Created Products', readonly=True)
    updated_count = fields.Integer('Updated Products', readonly=True)
    error_count = fields.Integer('Errors', readonly=True)
    sync_results = fields.Text('Sync Results', readonly=True)
    
    def action_sync_products(self):
        """Execute the product synchronization"""
        self.ensure_one()
        
        try:
            # Validate input
            if self.sync_type == 'search' and not self.search_query:
                raise ValidationError(_('Search query is required for search sync type'))
            
            if self.sync_type == 'part_number' and not self.part_number:
                raise ValidationError(_('Part number is required for part number sync type'))
            
            # Prepare parameters
            search_query = self.search_query if self.sync_type == 'search' else None
            part_number = self.part_number if self.sync_type == 'part_number' else None
            limit = self.limit if self.sync_type in ['search', 'all'] else 1
            
            # Execute sync
            product_model = self.env['finditparts.product']
            results = product_model.sync_products_from_api(
                search_query=search_query,
                part_number=part_number,
                limit=limit
            )
            
            # Update wizard with results
            self.created_count = results['created']
            self.updated_count = results['updated']
            self.error_count = len(results['errors'])
            self.sync_completed = True
            
            # Format results message
            result_lines = [
                f"Sync completed successfully!",
                f"Created: {self.created_count} products",
                f"Updated: {self.updated_count} products",
                f"Errors: {self.error_count}"
            ]
            
            if results['errors']:
                result_lines.append("\nErrors:")
                for error in results['errors'][:5]:  # Show first 5 errors
                    result_lines.append(f"- {error}")
                if len(results['errors']) > 5:
                    result_lines.append(f"... and {len(results['errors']) - 5} more errors")
            
            self.sync_results = '\n'.join(result_lines)
            
            # Return to same wizard to show results
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'finditparts.product.sync.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'name': _('Sync Results')
            }
            
        except Exception as e:
            _logger.error(f"Sync wizard failed: {str(e)}")
            self.sync_results = f"Sync failed: {str(e)}"
            self.error_count = 1
            self.sync_completed = True
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'finditparts.product.sync.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'name': _('Sync Error')
            }
    
    def action_view_created_products(self):
        """View created products"""
        self.ensure_one()
        
        domain = [
            ('create_date', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0)),
            ('sync_status', '=', 'synced')
        ]
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finditparts.product',
            'view_mode': 'tree,form',
            'domain': domain,
            'name': _('Recently Synced Products'),
            'target': 'current'
        }
    
    def action_view_odoo_products(self):
        """View created Odoo products"""
        self.ensure_one()
        
        # Find finditparts products created today that have odoo products
        finditparts_products = self.env['finditparts.product'].search([
            ('create_date', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0)),
            ('odoo_product_id', '!=', False)
        ])
        
        odoo_product_ids = finditparts_products.mapped('odoo_product_id.id')
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', odoo_product_ids)],
            'name': _('Created Odoo Products'),
            'target': 'current'
        }

