from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class ProductRequestController(http.Controller):
    """Controller to handle product availability requests from website"""
    
    @http.route('/shop/product/request_availability', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def request_product_availability(self, product_id, email, message, **kwargs):
        """
        Create a CRM lead when a customer requests information about an out-of-stock product
        
        Args:
            product_id: ID of the product being requested
            email: Customer's email address
            message: Customer's message/inquiry
            
        Returns:
            dict: Success status and message
        """
        try:
            # Get the product
            product = request.env['product.template'].sudo().browse(int(product_id))
            
            if not product.exists():
                return {'success': False, 'error': 'Product not found'}
            
            # Validate email
            if not email or '@' not in email:
                return {'success': False, 'error': 'Invalid email address'}
            
            # Create a lead in CRM
            lead_vals = {
                'name': f'Product Request: {product.name}',
                'type': 'opportunity',
                'email_from': email,
                'description': f"""
Product Requested: {product.name}
SKU: {product.default_code or 'N/A'}
Customer Message: {message or 'No message provided'}

This lead was automatically created from a product availability request on the website.
                """.strip(),
                'tag_ids': [(6, 0, [])],  # You can add specific tags if needed
                'user_id': False,  # Unassigned, or you can assign to a specific user
            }
            
            lead = request.env['crm.lead'].sudo().create(lead_vals)
            
            _logger.info(f"Created CRM lead {lead.id} for product request: {product.name} from {email}")
            
            # Optionally, send an email notification to sales team
            try:
                # Get contact email from configuration
                config = request.env['finditparts.config'].sudo().search([('active', '=', True)], limit=1)
                contact_email = config.contact_email if config else 'tmjhosep@gmail.com'
                
                mail_values = {
                    'email_to': contact_email,
                    'subject': f'New Product Request: {product.name}',
                    'body_html': f"""
                        <p><strong>New product availability request received:</strong></p>
                        <ul>
                            <li><strong>Product:</strong> {product.name}</li>
                            <li><strong>SKU:</strong> {product.default_code or 'N/A'}</li>
                            <li><strong>Customer Email:</strong> {email}</li>
                            <li><strong>Message:</strong> {message or 'No message'}</li>
                        </ul>
                        <p><a href="/web#id={lead.id}&model=crm.lead&view_type=form">View Lead in CRM</a></p>
                    """,
                }
                request.env['mail.mail'].sudo().create(mail_values).send()
            except Exception as mail_error:
                _logger.warning(f"Failed to send email notification: {mail_error}")
            
            return {
                'success': True,
                'message': 'Thank you! We will contact you soon regarding this product.'
            }
            
        except Exception as e:
            _logger.error(f"Error creating product request: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred. Please try again or contact us directly.'
            }
