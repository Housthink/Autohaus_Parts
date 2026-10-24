from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import html_escape
import logging
import re
import os
import base64
import json
import requests
from datetime import datetime
from urllib.parse import urlsplit

DEFAULT_IMAGE_URL = '/finditparts_integration/static/img/default_product.png'
BEST_SELLER_LIMIT = 100
BEST_SELLER_CACHE_TTL = 3600  # seconds

_logger = logging.getLogger(__name__)


class FindinPartProduct(models.Model):
    _name = 'finditparts.product'
    _description = 'FindinPart Product'
    _rec_name = 'sku'
    _order = 'last_sync_date desc'

    sku = fields.Char('SKU', required=True, index=True)
    finditparts_id = fields.Char('FindinPart ID', index=True)
    brand = fields.Char('Brand')
    manufacturer = fields.Char('Manufacturer')
    part_number = fields.Char('Part Number')
    
    name = fields.Char('Product Name', required=True)
    description = fields.Text('Description')
    long_description = fields.Html('Long Description')
    specifications = fields.Text('Technical Specifications')
    
    category_id = fields.Many2one('product.category', 'Category')
    subcategory_id = fields.Many2one('product.category', 'Subcategory')
    public_categ_ids = fields.Many2many(
        'product.public.category',
        'finditparts_product_public_categ_rel',
        'finditparts_product_id',
        'public_categ_id',
        string='Website Categories',
    )
    tags = fields.Many2many('product.tag', string='Tags')
    
    list_price = fields.Float('List Price', digits=(10, 2))
    cost_price = fields.Float('Cost Price', digits=(10, 2))
    api_price = fields.Float('API Price', digits=(10, 2))
    api_cost = fields.Float('API Cost', digits=(10, 2))
    msrp_price = fields.Float('MSRP Price', digits=(10, 2))
    discount_percent = fields.Float(
        'Discount (%)', digits=(10, 2),
        help='Discount reported by FinditParts or calculated from MSRP and sale price.',
    )
    discount_amount = fields.Float(
        'Discount Amount', digits=(10, 2),
        help='Difference between the comparable/original price and the sale price.',
    )
    currency_id = fields.Many2one('res.currency', 'Currency', default=lambda self: self.env.company.currency_id)
    
    stock_quantity = fields.Float('Stock Quantity', default=0)
    estimated_days_to_deliver = fields.Integer(
        'Estimated Days to Deliver',
        default=0,
        help='Días estimados de entrega informados por la API de FinditParts.',
    )
    min_stock_level = fields.Float('Minimum Stock Level', default=0)
    max_stock_level = fields.Float('Maximum Stock Level')
    stock_status = fields.Selection([
        ('in_stock', 'In Stock'),
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('discontinued', 'Discontinued'),
        ('pre_order', 'Pre-Order'),
    ], string='Stock Status', default='out_of_stock')
    
    image_url = fields.Char('Image URL')
    image_ids = fields.Many2many('ir.attachment', string='Product Images')
    datasheet_url = fields.Char('Datasheet URL')
    video_url = fields.Char('Video URL')
    
    weight = fields.Float('Weight (kg)')
    length = fields.Float('Length (cm)')
    width = fields.Float('Width (cm)')
    height = fields.Float('Height (cm)')
    
    # Computed field for price with margin
    sale_price_with_margin = fields.Float('Sale Price (with margin)', compute='_compute_sale_price_with_margin', store=True,
                                         help='List price plus configured margin percentage')
    
    compatible_models = fields.Text('Compatible Models')
    compatible_years = fields.Char('Compatible Years')
    compatible_makes = fields.Char('Compatible Makes')
    sellable = fields.Boolean('Sellable', default=True)
    best_seller = fields.Boolean('Best Seller', default=False)
    availability_message = fields.Text('Availability Message')
    seo_keywords = fields.Text('SEO Keywords')
    
    odoo_product_id = fields.Many2one('product.template', 'Odoo Product', ondelete='set null')
    sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('failed', 'Failed'),
        ('outdated', 'Outdated'),
    ], string='Sync Status', default='pending')
    last_sync_date = fields.Datetime('Last Sync Date')
    next_sync_date = fields.Datetime('Next Sync Date')
    sync_errors = fields.Text('Sync Errors')
    
    active = fields.Boolean('Active', default=True)
    create_date = fields.Datetime('Created Date', readonly=True)
    write_date = fields.Datetime('Last Updated', readonly=True)
    
    # SQL constraints removed for Odoo 19 compatibility
    # Uniqueness will be enforced through database indexes and validation methods
    
    @api.constrains('sku')
    def _check_unique_sku(self):
        for record in self:
            if record.sku:
                existing = self.search([('sku', '=', record.sku), ('id', '!=', record.id)])
                if existing:
                    raise ValidationError(_('SKU must be unique! SKU "%s" already exists.') % record.sku)
    
    @api.depends('list_price')
    def _compute_sale_price_with_margin(self):
        """Calculate sale price with configured margin percentage"""
        for record in self:
            # Get active configuration
            config = self.env['finditparts.config'].search([('active', '=', True)], limit=1)
            margin_percent = config.price_margin_percent if config else 10.0
            
            # Calculate price with margin
            if record.list_price:
                record.sale_price_with_margin = record.list_price * (1 + margin_percent / 100.0)
            else:
                record.sale_price_with_margin = 0.0

    @staticmethod
    def _is_placeholder_image_url(url):
        """Detect FinditParts placeholder/default images so they are not stored"""
        if not url:
            return False
        if url == DEFAULT_IMAGE_URL:
            return False
        lowered = url.lower()
        placeholder_markers = [
            'no-image-small',
            'no-image-large',
            'no-image-product',
            'noimage',
            'placeholder',
            '/assets/no-image',
            '/assets/default',
            'default_product.png',
        ]
        if any(marker in lowered for marker in placeholder_markers):
            return True

        # Some CDN URLs embed metadata in a base64 segment; decode to inspect the "key"
        try:
            # Extract last path segment without querystring or extension
            path = urlsplit(url).path or ''
            filename = path.rsplit('/', 1)[-1]
            token = filename.split('?', 1)[0].split('.', 1)[0]
            if token:
                padded = token + '=' * (-len(token) % 4)
                decoded = base64.urlsafe_b64decode(padded).decode('utf-8', errors='ignore')
                try:
                    payload = json.loads(decoded)
                    if isinstance(payload, dict):
                        key_val = str(payload.get('key', '')).lower()
                        if any(marker in key_val for marker in placeholder_markers):
                            return True
                    else:
                        decoded_lower = decoded.lower()
                        if any(marker in decoded_lower for marker in placeholder_markers):
                            return True
                except Exception:
                    decoded_lower = decoded.lower()
                    if any(marker in decoded_lower for marker in placeholder_markers):
                        return True
        except Exception:
            # If decoding fails, fall back to non-placeholder
            return False

        return False
    

    @api.constrains('finditparts_id')
    def _check_unique_finditparts_id(self):
        for record in self:
            if record.finditparts_id:
                existing = self.search([('finditparts_id', '=', record.finditparts_id), ('id', '!=', record.id)])
                if existing:
                    raise ValidationError(_('FindinPart ID must be unique! ID "%s" already exists.') % record.finditparts_id)
    
    @api.constrains('stock_quantity', 'min_stock_level')
    def _check_stock_levels(self):
        for record in self:
            if record.stock_quantity < 0:
                raise ValidationError(_('Stock quantity cannot be negative'))
            if record.min_stock_level < 0:
                raise ValidationError(_('Minimum stock level cannot be negative'))
    
    def update_stock_status(self):
        """Update stock status based on current stock levels"""
        for record in self:
            if record.stock_quantity <= 0:
                record.stock_status = 'out_of_stock'
            elif record.stock_quantity <= record.min_stock_level:
                record.stock_status = 'low_stock'
            else:
                record.stock_status = 'in_stock'
    
    def sync_to_odoo(self):
        """Sync this product to Odoo product catalog"""
        self.ensure_one()
        try:
            config = self.env['finditparts.config'].get_active_config()
            product_vals = {}
            sale_delay = (self.estimated_days_to_deliver or 0) + 2

            best_seller_skus = self._get_best_seller_skus()
            if best_seller_skus is not None:
                self.best_seller = (self.sku or '').strip() in best_seller_skus
            
            # SIEMPRE permitir venta en Odoo para que aparezca en la web
            # El control de si se puede comprar o no se hace mediante el mensaje en el website
            sale_allowed = True
            
            # TEMPORAL: Forzar stock=0 para el primer producto (para testing del mensaje)
            # Contar cuántos productos ya existen en Odoo
            existing_count = self.env['product.template'].search_count([])
            
            # Si es el primer producto, forzar stock=0 (pero mantener sale_ok=True)
            if existing_count == 0:
                original_stock = self.stock_quantity
                self.stock_quantity = 0
                _logger.info(f"🔴 TESTING MODE: Forzando stock=0 para el primer producto: {self.sku}")
                _logger.info(f"   Stock original: {original_stock} → Forzado a: 0")
                _logger.info(f"   sale_ok: {sale_allowed} (siempre True para aparecer en web)")
            
            website_description = self._get_website_description_html()
            sale_description = self._get_sale_description_text()
            # Use price with margin instead of base price
            list_price_value = self.sale_price_with_margin or self._get_odoo_sale_price()
            cost_price_value = self._get_odoo_cost_price()
            brand_tag = self._ensure_brand_tag()
            
            if not self.odoo_product_id:
                # Create new Odoo product
                product_vals = {
                    'name': self.name,
                    'description': self.description or '',
                    'description_sale': sale_description,
                    'website_description': website_description or False,
                    'list_price': list_price_value,
                    # standard_price write can be restricted; do it with sudo and ignore errors
                    'categ_id': self.category_id.id if self.category_id else (config.default_category_id.id if config and config.default_category_id else False),
                    'default_code': self.sku,
                    'weight': self.weight or 0.0,
                    'volume': (self.length or 0) * (self.width or 0) * (self.height or 0) / 1000000,  # m³
                    'sale_ok': sale_allowed,
                    'purchase_ok': True,
                    'best_seller': self.best_seller,
                }
                if 'sale_delay' in self.env['product.template']._fields:
                    product_vals['sale_delay'] = sale_delay
                if brand_tag:
                    product_vals['product_tag_ids'] = [(4, brand_tag.id)]
                if 'public_categ_ids' in self.env['product.template']._fields:
                    # Always replace existing website categories with the new one
                    product_vals['public_categ_ids'] = [(6, 0, self.public_categ_ids.ids)]
                if self.seo_keywords and 'website_meta_keywords' in self.env['product.template']._fields:
                    product_vals['website_meta_keywords'] = self.seo_keywords
                
                # Determine product type field depending on Odoo version/instance
                try:
                    pt = self.env['product.template']
                    if 'detailed_type' in pt._fields:
                        field = pt._fields['detailed_type']
                        sel = field.selection(self.env) if callable(getattr(field, 'selection', None)) else getattr(field, 'selection', None)
                        allowed = [k for k, _ in (sel or [])]
                        val = 'product' if 'product' in allowed else ('consumable' if 'consumable' in allowed else (allowed[0] if allowed else 'product'))
                        product_vals['detailed_type'] = val
                    elif 'type' in pt._fields:
                        field = pt._fields['type']
                        sel = field.selection(self.env) if callable(getattr(field, 'selection', None)) else getattr(field, 'selection', None)
                        allowed = [k for k, _ in (sel or [])]
                        val = 'product' if 'product' in allowed else ('consu' if 'consu' in allowed else (allowed[0] if allowed else 'product'))
                        product_vals['type'] = val
                except Exception:
                    # Fallbacks
                    if 'type' in self.env['product.template']._fields:
                        product_vals.setdefault('type', 'product')
                
                # Add website/eCommerce fields if enabled in config
                if config and config.auto_publish_website:
                    product_vals.update({
                        'is_published': True,
                        'website_published': True,
                    })
                
                odoo_product = self.env['product.template'].sudo().create(product_vals)
                template_discount_vals = {
                    'finditparts_discount_percent': self.discount_percent,
                }
                if 'compare_list_price' in odoo_product._fields:
                    template_discount_vals['compare_list_price'] = self.msrp_price or False
                odoo_product.sudo().write(template_discount_vals)
                # Try writing cost separately with sudo (ignore failure)
                try:
                    if self.cost_price is not None or self.api_cost is not None:
                        odoo_product.sudo().write({'standard_price': cost_price_value})
                except Exception as cost_err:
                    _logger.warning(f"Could not set standard_price for {self.sku}: {cost_err}")
                # Set SEO keywords if present and field exists
                try:
                    if self.seo_keywords and 'website_meta_keywords' in odoo_product._fields:
                        odoo_product.sudo().write({'website_meta_keywords': self.seo_keywords})
                except Exception as seo_err:
                    _logger.warning(f"Could not set website_meta_keywords for {self.sku}: {seo_err}")
                
                self.odoo_product_id = odoo_product.id
                
                # Download and attach product image if available
                if self.image_url:
                    try:
                        import requests
                        image_data = False
                        if self.image_url == DEFAULT_IMAGE_URL:
                            image_data = self._get_default_image_data()
                        elif not self._is_placeholder_image_url(self.image_url):
                            response = requests.get(self.image_url, timeout=10)
                            if response.status_code == 200:
                                image_data = base64.b64encode(response.content)
                        if image_data:
                            odoo_product.sudo().write({'image_1920': image_data})
                            _logger.info(f"Image set for product {self.sku}")
                    except Exception as img_error:
                        _logger.warning(f"Failed to download image for {self.sku}: {str(img_error)}")
                
                
                # Initial stock - Odoo 19 compatible method
                try:
                    if config and config.default_warehouse_id and self.stock_quantity > 0 and (config.auto_update_stock or True):
                        # En Odoo 19, usar el método oficial para actualizar stock
                        location_id = config.default_warehouse_id.lot_stock_id
                        product_variant = odoo_product.product_variant_id
                        
                        # Usar el método oficial de Odoo para actualizar cantidad disponible
                        # Esto actualiza correctamente qty_available
                        self.env['stock.quant'].sudo().with_context(
                            inventory_mode=True
                        )._update_available_quantity(
                            product_variant,
                            location_id,
                            self.stock_quantity,
                        )
                        _logger.info(f"Stock set to {self.stock_quantity} for product {self.sku} using _update_available_quantity")
                except Exception as inv_err:
                    _logger.warning(f"Stock init skipped for {self.sku}: {inv_err}")
            else:
                # Update existing product
                update_vals = {}
                if config and config.auto_update_prices:
                    update_vals.update({
                        'list_price': list_price_value,
                    })
                
                # Update basic info
                update_vals.update({
                    'name': self.name,
                    'description': self.description or '',
                    'description_sale': sale_description,
                    'website_description': website_description or False,
                    'weight': self.weight or 0.0,
                    'sale_ok': sale_allowed,
                    'best_seller': self.best_seller,
                })
                if 'sale_delay' in self.env['product.template']._fields:
                    update_vals['sale_delay'] = sale_delay
                if self.seo_keywords and 'website_meta_keywords' in self.env['product.template']._fields:
                    update_vals['website_meta_keywords'] = self.seo_keywords
                if brand_tag:
                    update_vals['product_tag_ids'] = [(4, brand_tag.id)]
                if self.category_id:
                    update_vals['categ_id'] = self.category_id.id
                if 'public_categ_ids' in self.env['product.template']._fields:
                    # Always replace existing website categories with the new one
                    update_vals['public_categ_ids'] = [(6, 0, self.public_categ_ids.ids)]
                if 'finditparts_discount_percent' in self.odoo_product_id._fields:
                    update_vals['finditparts_discount_percent'] = self.discount_percent
                if 'compare_list_price' in self.odoo_product_id._fields:
                    update_vals['compare_list_price'] = self.msrp_price or False
                
                if update_vals:
                    self.odoo_product_id.sudo().write(update_vals)
                
                # Update cost separately (may be restricted)
                try:
                    if config and config.auto_update_prices and (self.cost_price is not None or self.api_cost is not None):
                        self.odoo_product_id.sudo().write({'standard_price': cost_price_value})
                except Exception as cost_err:
                    _logger.warning(f"Could not update standard_price for {self.sku}: {cost_err}")
                # Update SEO keywords if available
                try:
                    if self.seo_keywords and 'website_meta_keywords' in self.odoo_product_id._fields:
                        self.odoo_product_id.sudo().write({'website_meta_keywords': self.seo_keywords})
                except Exception as seo_err:
                    _logger.warning(f"Could not update website_meta_keywords for {self.sku}: {seo_err}")

                # Update or clear product image
                try:
                    if self.odoo_product_id:
                        image_data = False
                        if self.image_url == DEFAULT_IMAGE_URL:
                            image_data = self._get_default_image_data()
                        elif self.image_url and not self._is_placeholder_image_url(self.image_url):
                            import requests
                            response = requests.get(self.image_url, timeout=10)
                            if response.status_code == 200:
                                image_data = base64.b64encode(response.content)

                        if image_data:
                            self.odoo_product_id.sudo().write({'image_1920': image_data})
                        else:
                            # Clear existing image if now flagged as placeholder or missing
                            self.odoo_product_id.sudo().write({'image_1920': False})
                except Exception as img_err:
                    _logger.warning(f"Image update skipped for {self.sku}: {img_err}")
                
                
                # Update stock - Odoo 19 compatible method
                try:
                    if config and config.auto_update_stock and config.default_warehouse_id:
                        location_id = config.default_warehouse_id.lot_stock_id
                        product_variant = self.odoo_product_id.product_variant_id
                        
                        # Obtener la cantidad actual
                        current_qty = product_variant.with_context(location=location_id.id).qty_available
                        
                        # Calcular la diferencia
                        qty_diff = self.stock_quantity - current_qty
                        
                        if qty_diff != 0:
                            # Usar el método oficial para actualizar la cantidad
                            self.env['stock.quant'].sudo().with_context(
                                inventory_mode=True
                            )._update_available_quantity(
                                product_variant,
                                location_id,
                                qty_diff,
                            )
                            _logger.info(f"Stock updated from {current_qty} to {self.stock_quantity} for product {self.sku}")
                except Exception as inv_err:
                    _logger.warning(f"Stock update skipped for {self.sku}: {inv_err}")
            
            self.sync_status = 'synced'
            self.last_sync_date = fields.Datetime.now()
            self.sync_errors = False
            self.update_stock_status()
            self._link_alternative_products()
            
            return True
            
        except Exception as e:
            _logger.error(f"Failed to sync product {self.sku}: {str(e)}")
            self.sync_status = 'failed'
            self.sync_errors = str(e)
            return False
    
    def _link_alternative_products(self):
        """Vincula productos alternativos (relacionados) al producto de Odoo.

        Usa como heuristica los productos publicados de la misma marca (tag);
        si no hay, usa los de la misma categoria. Esto alimenta la seccion
        nativa "Productos relacionados" del website.
        """
        odoo_product = self.odoo_product_id
        if not odoo_product:
            return
        Template = self.env['product.template'].sudo()
        alternatives = Template.browse()

        brand_tags = odoo_product.product_tag_ids
        if brand_tags:
            alternatives = Template.search([
                ('id', '!=', odoo_product.id),
                ('is_published', '=', True),
                ('sale_ok', '=', True),
                ('product_tag_ids', 'in', brand_tags.ids),
            ], limit=8)

        if not alternatives and odoo_product.public_categ_ids:
            alternatives = Template.search([
                ('id', '!=', odoo_product.id),
                ('is_published', '=', True),
                ('sale_ok', '=', True),
                ('public_categ_ids', 'in', odoo_product.public_categ_ids.ids),
            ], limit=8)

        if alternatives:
            odoo_product.sudo().write({
                'alternative_product_ids': [(6, 0, alternatives.ids)],
            })
    
    def action_view_odoo_product(self):
        """Open the related Odoo product"""
        self.ensure_one()
        if self.odoo_product_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.template',
                'res_id': self.odoo_product_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False
    
    def action_sync_now(self):
        """Manually trigger sync for this product"""
        self.ensure_one()
        result = self.sync_to_odoo()
        if result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Product synced successfully'),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Product sync failed'),
                    'type': 'danger',
                }
            }
    
    def _extract_attribute_pairs(self, product_data):
        """Return list of (label, value) attribute tuples from API data.

        Incluye tanto los atributos del producto (PIES product_attributes)
        como la informacion adicional (extended_product_informations), que
        juntos forman las especificaciones del producto.
        """
        attribute_pairs = []
        attribute_map = product_data.get('attributes')
        if isinstance(attribute_map, dict):
            for key, value in attribute_map.items():
                if value is None:
                    continue
                label = key.replace('_', ' ').title()
                attribute_pairs.append((label, value))
        pies_data = product_data.get('pies_data') or {}
        for attr in pies_data.get('product_attributes') or []:
            name = attr.get('name')
            value = attr.get('value')
            if name and value:
                attribute_pairs.append((name, value))
        for info in pies_data.get('extended_product_informations') or []:
            name = info.get('description')
            value = info.get('value')
            if name and value:
                attribute_pairs.append((name, value))
        return attribute_pairs
    
    def _build_html_description(self, product_data, attribute_pairs=None, related_parts=None):
        """Genera la descripcion del producto en la web.

        Muestra la informacion separada por pestanas (tabs):
          - Descripcion
          - Especificaciones
          - Compatibilidad
          - Garantia y Devoluciones

        Las tres primeras se alimentan de los datos del producto; la ultima es
        contenido estatico traducido. El estilo vive en el CSS del modulo
        (autohaus_product_facts.css); aqui solo se genera el HTML semantico.
        """
        attribute_pairs = attribute_pairs or []
        sections = []
        part_number_re = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]*$')

        def format_text(value):
            if value in (None, False):
                return ''
            text = str(value)
            text = re.sub(r'<(script|style)[^>]*>.*?</\\1>', '', text,
                          flags=re.IGNORECASE | re.DOTALL)
            if re.search(r'<[^>]+>', text):
                return text
            return html_escape(text).replace('\n', '<br/>')

        def build_rows(rows, as_links=False):
            """Filas etiqueta/valor para una pestana."""
            def format_value(label, value):
                formatted = format_text(value)
                if as_links and part_number_re.match(value or ''):
                    href = '/shop?search=%s' % requests.utils.quote(value or '')
                    return "<a href='%s' class='o_autohaus_compat_link'>%s</a>" % (href, formatted)
                return formatted
            
            body = ''.join(
                f"<div class='o_autohaus_facts_row'>"
                f"<span class='o_autohaus_facts_label'>{format_text(label)}</span>"
                f"<span class='o_autohaus_facts_value'>{format_value(label, value)}</span>"
                f"</div>"
                for label, value in rows if value not in (None, '', [])
            )
            if not body:
                return ''
            return f"<div class='o_autohaus_facts_table'>{body}</div>"

        def build_text_block(title, body):
            """Bloque de texto con subtitulo y parrafo."""
            body = format_text(body)
            if not body:
                return ''
            return (
                f"<h4 class='o_autohaus_facts_subtitle'>{format_text(title)}</h4>"
                f"<div class='o_autohaus_facts_prose'>{body}</div>"
            )

        def build_shipping_info(product_data, current_variant):
            """Construye información de entrega y envío."""
            shipping_items = []
            
            # Tiempo estimado de entrega
            estimated_days = current_variant.get('estimated_days_to_deliver')
            if estimated_days:
                shipping_items.append(f"<strong>Tiempo estimado de entrega:</strong> {estimated_days} días hábiles")
            
            # Fecha estimada de envío
            estimated_ship = current_variant.get('estimated_ship_date')
            if estimated_ship:
                try:
                    ship_date = datetime.fromisoformat(estimated_ship.replace('Z', '+00:00'))
                    shipping_items.append(f"<strong>Fecha estimada de envío:</strong> {ship_date.strftime('%d de %B de %Y')}")
                except:
                    pass
            
            # Fecha estimada de entrega
            estimated_delivery = current_variant.get('estimated_delivery_date_ground')
            if estimated_delivery:
                try:
                    delivery_date = datetime.fromisoformat(estimated_delivery.replace('Z', '+00:00'))
                    shipping_items.append(f"<strong>Fecha estimada de entrega:</strong> {delivery_date.strftime('%d de %B de %Y')}")
                except:
                    pass
            
            # Ubicación del vendedor
            location = current_variant.get('location')
            if location:
                shipping_items.append(f"<strong>Ubicación:</strong> {location}")
            
            # Notas de envío de purchase_notes
            purchase_notes = product_data.get('purchase_notes') or []
            for note in purchase_notes:
                note_type = note.get('type', '')
                html_message = note.get('html_message', '')
                if note_type == 'SHIPPING_MESSAGE' and html_message:
                    shipping_items.append(html_message)
                elif note_type == 'SHIPPING_PROMISE' and html_message:
                    shipping_items.append(html_message)
            
            if not shipping_items:
                return ''
            
            content = '<ul class="o_autohaus_shipping_list">'
            for item in shipping_items:
                content += f'<li>{item}</li>'
            content += '</ul>'
            
            return f"<div class='o_autohaus_shipping_info'>{content}</div>"

        # --- Descripcion ---------------------------------------------------
        pies_data = product_data.get('pies_data') or {}
        descriptions = pies_data.get('descriptions') or []

        def pies_value(code):
            for item in descriptions:
                if item.get('description_code') == code and item.get('value'):
                    return item.get('value')
            return ''

        core_description = (
            product_data.get('short_description')
            or product_data.get('long_description')
            or product_data.get('description')
        )
        features = pies_value('FAB') or pies_value('MKT')
        description_content = ''.join([
            build_text_block('Descripción del producto', core_description),
            build_text_block('Características y beneficios', features),
        ])

        # --- Especificaciones técnicas -------------------------------------
        specs_content = build_rows(attribute_pairs)

        # --- Datos clave del producto (Quick Facts) ----------------------
        breadcrumbs = product_data.get('breadcrumbs_ancestors') or []
        category_label = None
        if isinstance(breadcrumbs, list) and breadcrumbs:
            category_label = (breadcrumbs[-1] or {}).get('name')

        current_variant = product_data.get('current_variant') or {}

        quick_facts_rows = []
        for label, value in [
            ('Número de parte', product_data.get('part_number') or product_data.get('sku')),
            ('Fabricante', product_data.get('manufacturer') or product_data.get('brand')),
            ('Descripción', core_description),
            ('Categoría', category_label),
            ('Condición', product_data.get('condition')),
            ('Vendible', 'Sí' if product_data.get('sellable') else 'No'),
            ('Stock', current_variant.get('quantity')),
            ('Peso (lbs)', product_data.get('weight')),
        ]:
            if value not in (None, '', []):
                quick_facts_rows.append((label, value))
        quick_facts_content = build_rows(quick_facts_rows)

        # --- Compatibilidad (referencias equivalentes) -------------------
        compat_rows = []
        for interchange in pies_data.get('part_interchanges') or []:
            part_number = interchange.get('part_number')
            if not part_number:
                continue
            brand = interchange.get('brand_label') or interchange.get('brand_aaiaid') or ''
            compat_rows.append((brand or 'OEM', part_number))
        compat_content = build_rows(compat_rows, as_links=True)

        # --- Garantia y Devoluciones (estatico, traducido) ----------------
        warranty_content = (
            "<h4 class='o_autohaus_facts_subtitle'>Garantía</h4>"
            "<div class='o_autohaus_facts_prose'><p>"
            "Todos nuestros productos están respaldados por la garantía del "
            "fabricante contra defectos de materiales y mano de obra bajo "
            "condiciones normales de uso."
            "</p></div>"
            "<h4 class='o_autohaus_facts_subtitle'>Devoluciones</h4>"
            "<div class='o_autohaus_facts_prose'><p>"
            "Política de devolución de 30 días. Los productos elegibles pueden "
            "devolverse por cualquier motivo dentro de los 30 días posteriores a "
            "la fecha de entrega, siempre que estén nuevos, en condición vendible "
            "y en su empaque original. El crédito se procesa dentro de 3 a 5 días "
            "hábiles desde la recepción de la pieza."
            "</p></div>"
            "<a class='o_autohaus_facts_more' href='/devoluciones'>Ver Más</a>"
        )

        # --- Entrega e información de envío --------------------------------
        shipping_info_content = build_shipping_info(product_data, current_variant)

        # --- Armar secciones ----------------------------------------------
        if description_content:
            sections.append(('o_autohaus_pane_description', 'Descripción', description_content))
        if specs_content:
            sections.append(('o_autohaus_pane_specs', 'Especificaciones técnicas', specs_content))
        if quick_facts_content:
            sections.append(('o_autohaus_pane_quick_facts', 'Ficha técnica', quick_facts_content))
        if compat_content:
            sections.append(('o_autohaus_pane_compat', 'Compatibilidad', compat_content))
        if shipping_info_content:
            sections.append(('o_autohaus_pane_shipping', 'Entrega e información de envío', shipping_info_content))
        sections.append(('o_autohaus_pane_warranty', 'Garantía y Devoluciones', warranty_content))

        if not sections:
            return ''

        if len(sections) == 1:
            _pane_id, title, content = sections[0]
            body = (
                f"<h3 class='o_autohaus_facts_title'>{format_text(title)}</h3>"
                f"{content}"
            )
        else:
            tabs = ''.join(
                f"<li class='nav-item'>"
                f"<a class='nav-link{' active' if index == 0 else ''}' "
                f"data-bs-toggle='tab' href='#{pane_id}'>{format_text(title)}</a>"
                f"</li>"
                for index, (pane_id, title, _content) in enumerate(sections)
            )
            panes = ''.join(
                f"<div class='tab-pane fade{' show active' if index == 0 else ''}' id='{pane_id}'>"
                f"{content}"
                f"</div>"
                for index, (pane_id, _title, content) in enumerate(sections)
            )
            body = (
                f"<ul class='nav nav-tabs o_autohaus_facts_tabs'>{tabs}</ul>"
                f"<div class='tab-content o_autohaus_facts_content'>{panes}</div>"
            )

        # 'container' de Odoo/Bootstrap: mismo ancho y padding que la fila
        # del producto (imagen + detalles), para que queden alineados.
        return (
            "<div class='o_autohaus_facts container'>"
            "<div class='o_autohaus_facts_panel'>"
            f"{body}"
            "</div>"
            "</div>"
        )

    def _build_availability_message(self, sellable, stock_qty=None):
        """Return an availability message when the product cannot be purchased online."""
        qty = stock_qty if stock_qty is not None else (self.stock_quantity or 0)
        # If sellable and has stock, no message needed
        if sellable and qty > 0:
            return False
        phone = "2304930"
        if not sellable:
            return _('This item is not available for online purchase. Please call %(phone)s for assistance.') % {'phone': phone}
        # No stock but we still want to show the product and provide a CTA
        return _('Out of stock. Call %(phone)s for availability or to order.') % {'phone': phone}
    
    def _get_odoo_sale_price(self):
        for value in [self.msrp_price, self.list_price, self.api_price]:
            if value not in (None, False):
                return value
        return 0.0
    
    def _get_odoo_cost_price(self):
        for value in [self.api_cost, self.cost_price]:
            if value not in (None, False):
                return value
        return 0.0
    
    def _get_website_description_html(self):
        base = self.long_description or self.description or ''
        if not isinstance(base, str):
            base = ''
        # Exclude availability/sellability messages and demo policy block from website description
        parts = [base]
        return ''.join([p for p in parts if p]) if any(parts) else ''

    
    def _strip_html_tags(self, value):
        if not isinstance(value, str):
            return ''
        return re.sub(r'<[^>]*>', '', value)
    
    def _get_sale_description_text(self):
        """Plain text for sale description (avoid HTML in SO/Invoices)"""
        base = self.description or self._strip_html_tags(self.long_description or '')
        message = ''
        if not self.sellable:
            message = self.availability_message or self._build_availability_message(False)
        parts = [p.strip() for p in [base, message] if p]
        return '\n'.join(parts)

    def _get_default_image_data(self):
        """Load default image from module static folder and return base64"""
        try:
            module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            img_path = os.path.join(module_path, 'static', 'img', 'default_product.png')
            with open(img_path, 'rb') as img_file:
                return base64.b64encode(img_file.read())
        except Exception as err:
            _logger.warning(f"Default image not found or unreadable: {err}")
            return False
    
    def _ensure_brand_tag(self, brand_name=None):
        """Find or create a product.tag record for the product brand.

        Returns the tag recordset (empty if the product has no brand).
        """
        brand_name = (brand_name or self.manufacturer or self.brand or '').strip()
        if not brand_name:
            return self.env['product.tag']
        Tag = self.env['product.tag'].sudo()
        tag = Tag.search([('name', '=ilike', brand_name)], limit=1)
        if not tag:
            tag = Tag.create({'name': brand_name})
            _logger.info(f"Created product.tag for brand: {brand_name}")
        return tag

    def _get_or_create_category_path(self, names, model):
        """Ensure a category hierarchy exists and return its records in order."""
        Category = self.env[model].sudo()
        parent = Category.browse()
        path = Category.browse()
        for name in names:
            name = (name or '').strip()
            if not name:
                continue
            category = Category.search([
                ('name', '=', name),
                ('parent_id', '=', parent.id if parent else False),
            ], limit=1)
            if not category:
                vals = {'name': name}
                if parent:
                    vals['parent_id'] = parent.id
                category = Category.create(vals)
                _logger.info(f"Created {model} category: {name}")
            path |= category
            parent = category
        return path

    def _ensure_categories(self, product_data):
        """Build inventory and website categories from the API breadcrumbs.

        Returns a vals dict with ``category_id`` (product.category) and
        ``public_categ_ids`` (product.public.category) when available.
        """
        breadcrumbs = (
            product_data.get('breadcrumbs_ancestors')
            or product_data.get('breadcrumbs')
            or []
        )
        names = []
        for breadcrumb in breadcrumbs:
            if isinstance(breadcrumb, dict):
                name = breadcrumb.get('name') or ''
            elif isinstance(breadcrumb, str):
                name = breadcrumb
            else:
                name = ''
            name = name.strip()
            if not name:
                continue
            if name.lower() in (
                'categories', 'all categories', 'home', 'shop',
                'manufacturer', 'manufacturers', 'brand', 'brands',
            ):
                continue
            names.append(name)

        manufacturer = (
            product_data.get('manufacturer')
            or product_data.get('brand')
            or ''
        ).strip()
        if manufacturer:
            names = [n for n in names if n.lower() != manufacturer.lower()]

        if not names:
            # Fallback to PIES category/subcategory when breadcrumbs are absent
            pies = product_data.get('pies_data') or {}
            names = [
                (pies.get('category') or '').strip(),
                (pies.get('subcategory') or '').strip(),
            ]
            names = [n for n in names if n]

        if not names:
            # The API sometimes only exposes a manufacturer breadcrumb; use a
            # bucket instead of turning the brand into a category.
            names = ['Uncategorized']

        vals = {}
        if not names:
            return vals

        inventory_path = self._get_or_create_category_path(names, 'product.category')
        if inventory_path:
            vals['category_id'] = inventory_path[-1].id

        if 'public_categ_ids' in self.env['product.template']._fields:
            website_path = self._get_or_create_category_path(names, 'product.public.category')
            if website_path:
                # Replace any previous website categories with the new leaf only
                vals['public_categ_ids'] = [(6, 0, [website_path[-1].id])]

        return vals

    @api.model
    def _get_best_seller_skus(self, client=None, force=False):
        """Return the part numbers currently ordered as best sellers.

        The API only exposes the ordering (``order=best_selling``), not sales
        figures. The result is cached for an hour to avoid an extra API call
        on every product request. Returns ``None`` when the API call fails so
        callers can keep the previous flags.
        """
        config = self.env['finditparts.config'].get_active_config()
        if not config:
            return None

        params = self.env['ir.config_parameter'].sudo()
        cache_key = 'finditparts_integration.best_sellers'
        cache_ts_key = 'finditparts_integration.best_sellers_ts'
        now = datetime.now()

        if not force:
            cached_value = params.get_param(cache_key)
            cached_ts = params.get_param(cache_ts_key)
            if cached_value and cached_ts:
                try:
                    age = (now - datetime.strptime(cached_ts, '%Y-%m-%d %H:%M:%S')).total_seconds()
                except ValueError:
                    age = None
                if age is not None and age < BEST_SELLER_CACHE_TTL:
                    try:
                        return set(json.loads(cached_value))
                    except (TypeError, ValueError):
                        pass

        from ..utils.api_client import FindinPartAPIClient
        client = client or FindinPartAPIClient(config)
        skus = set()
        page = 1
        try:
            while len(skus) < BEST_SELLER_LIMIT:
                limit = min(100, BEST_SELLER_LIMIT - len(skus))
                response = client.get_best_sellers(limit=limit, page=page)
                if response is None:
                    return None
                products = (response or {}).get('products') or []
                if not products:
                    break
                for product in products:
                    part_number = (product.get('part_number') or '').strip()
                    if part_number:
                        skus.add(part_number)
                pagination = (response or {}).get('pagination') or {}
                total_pages = pagination.get('total_pages') or page
                if page >= total_pages:
                    break
                page += 1
        except Exception as err:
            _logger.warning("Could not fetch best sellers from API: %s", err)
            return None

        params.set_param(cache_key, json.dumps(sorted(skus)))
        params.set_param(cache_ts_key, now.strftime('%Y-%m-%d %H:%M:%S'))
        return skus

    @api.model
    def _apply_best_seller_flags(self, skus):
        """Mark matching products as best sellers and clear the previous ones."""
        if skus is None:
            return
        skus = sorted({(sku or '').strip() for sku in skus if (sku or '').strip()})
        if not skus:
            _logger.info("Best seller list is empty; keeping existing flags")
            return

        FindinPartProduct = self.sudo()
        marked = FindinPartProduct.search([
            ('sku', 'in', skus),
            ('best_seller', '=', False),
        ])
        if marked:
            marked.write({'best_seller': True})
        cleared = FindinPartProduct.search([
            ('best_seller', '=', True),
            ('sku', 'not in', skus),
        ])
        if cleared:
            cleared.write({'best_seller': False})

        Template = self.env['product.template'].sudo()
        marked_templates = Template.search([
            ('default_code', 'in', skus),
            ('best_seller', '=', False),
        ])
        if marked_templates:
            marked_templates.write({'best_seller': True})
        cleared_templates = Template.search([
            ('best_seller', '=', True),
            ('default_code', 'not in', skus),
        ])
        if cleared_templates:
            cleared_templates.write({'best_seller': False})

        _logger.info(
            "Best seller flags updated: %s products marked, %s cleared",
            len(marked), len(cleared),
        )

    @api.model
    def create_from_api_json(self, json_data):
        """Create or update a finditparts.product record from API JSON data
        Returns (record, created_bool)
        """
        try:
            # Extract product data from JSON
            match_candidates = []
            
            if 'product' in json_data:
                product_data = json_data['product']
            elif 'main_part' in json_data:
                product_data = json_data['main_part']
            else:
                product_data = json_data
            
            if isinstance(json_data, dict):
                match_candidates = json_data.get('part_number_matches') or []
            
            match_product = None
            if match_candidates:
                def _variant_qty(candidate):
                    cv = candidate.get('current_variant') or {}
                    return float(cv.get('quantity') or cv.get('on_hand') or 0)

                # Prefer a candidate with stock, otherwise fall back to same part_number, else first
                match_product = next(
                    (c for c in match_candidates if _variant_qty(c) > 0),
                    None
                ) or next(
                    (candidate for candidate in match_candidates
                     if candidate.get('part_number') == product_data.get('part_number')),
                    None
                ) or match_candidates[0]
            
            if match_product:
                for field in ['pies_data', 'descriptions', 'product_images', 'attributes']:
                    if not product_data.get(field) and match_product.get(field):
                        product_data[field] = match_product[field]
                if not product_data.get('long_description') and match_product.get('long_description'):
                    product_data['long_description'] = match_product['long_description']
                if not product_data.get('short_description') and match_product.get('short_description'):
                    product_data['short_description'] = match_product['short_description']
                if not product_data.get('current_variant') and match_product.get('current_variant'):
                    product_data['current_variant'] = match_product['current_variant']
                if not product_data.get('msrp') and match_product.get('msrp'):
                    product_data['msrp'] = match_product['msrp']
                if not product_data.get('attributes') and match_product.get('attributes'):
                    product_data['attributes'] = match_product['attributes']
            
            attribute_pairs = self._extract_attribute_pairs(product_data)
            
            # Build SEO-friendly name including manufacturer + part number + short description
            manufacturer = product_data.get('manufacturer') or product_data.get('brand') or ''
            part_number = product_data.get('part_number', '')
            short_desc = product_data.get('short_description', '')
            seo_parts = [p for p in [manufacturer, part_number, short_desc] if p]
            seo_name = ' - '.join(seo_parts) if seo_parts else (part_number or short_desc)

            # Map API fields to model fields
            vals = {
                'finditparts_id': str(product_data.get('id', '')),
                'sku': part_number,
                'part_number': part_number,
                'name': seo_name or short_desc or part_number,
                'description': short_desc or seo_name or part_number,
                'long_description': product_data.get('long_description', ''),
                'manufacturer': manufacturer,
                'brand': manufacturer,
            }
            
            # Handle pricing from current variant
            current_variant = product_data.get('current_variant', {})
            if current_variant:
                variant_price = float(
                    current_variant.get('sale_price')
                    or current_variant.get('account_price')
                    or current_variant.get('price', 0)
                    or 0
                )
                variant_cost = float(current_variant.get('cost', 0) or 0)
                vals.update({
                    'api_price': variant_price,
                    'api_cost': variant_cost,
                    'list_price': variant_price,
                    'cost_price': variant_cost,
                    'stock_quantity': float(current_variant.get('quantity', 0) or 0),
                })

                discount_value = (
                    current_variant.get('discount_percent')
                    or current_variant.get('discount_percentage')
                    or current_variant.get('discount')
                    or product_data.get('discount_percent')
                    or product_data.get('discount_percentage')
                    or product_data.get('discount')
                )
                original_value = (
                    current_variant.get('original_price')
                    or current_variant.get('regular_price')
                    or current_variant.get('list_price')
                    or current_variant.get('msrp')
                    or product_data.get('msrp')
                )
                try:
                    original_price = float(original_value or 0)
                    explicit_discount = float(discount_value or 0)
                    if explicit_discount > 1:
                        discount_percent = explicit_discount
                    elif explicit_discount:
                        discount_percent = explicit_discount * 100
                    elif original_price > variant_price > 0:
                        discount_percent = ((original_price - variant_price) / original_price) * 100
                    else:
                        discount_percent = 0.0
                    if original_price <= variant_price:
                        original_price = 0.0
                    vals.update({
                        'discount_percent': max(0.0, discount_percent),
                        'discount_amount': max(0.0, original_price - variant_price),
                    })
                except (TypeError, ValueError):
                    _logger.warning('Invalid discount data for %s', part_number)
            
            if isinstance(current_variant, dict):
                estimated_days = current_variant.get('estimated_days_to_deliver')
                if estimated_days not in (None, ''):
                    try:
                        vals['estimated_days_to_deliver'] = max(0, int(float(estimated_days)))
                    except (TypeError, ValueError):
                        _logger.warning(
                            'Invalid estimated_days_to_deliver for %s: %r',
                            vals.get('sku'), estimated_days,
                        )

            # Handle MSRP
            if product_data.get('msrp'):
                msrp_value = float(product_data['msrp'])
                vals.update({
                    'msrp_price': msrp_value,
                })
                sale_value = vals.get('list_price', 0.0)
                if msrp_value > sale_value > 0 and not vals.get('discount_percent'):
                    vals['discount_percent'] = ((msrp_value - sale_value) / msrp_value) * 100
                    vals['discount_amount'] = msrp_value - sale_value
            
            # Handle weight
            if product_data.get('weight'):
                try:
                    weight_lbs = float(product_data['weight'])
                    vals['weight'] = weight_lbs * 0.453592
                except (ValueError, TypeError):
                    vals['weight'] = 0.0
            
            # Handle images
            image_url = False
            product_images = product_data.get('product_images', [])
            if product_images and len(product_images) > 0:
                # Use the first image's product size URL
                first_image = product_images[0]
                if 'product' in first_image and 'jpeg' in first_image['product']:
                    image_url = first_image['product']['jpeg']
            # Fallbacks: API often provides top-level image fields
            if not image_url:
                if product_data.get('image'):
                    image_url = product_data.get('image')
                elif product_data.get('image_thumbnail'):
                    image_url = product_data.get('image_thumbnail')

            # Replace placeholder/missing images with local default
            if not image_url or self._is_placeholder_image_url(image_url):
                image_url = DEFAULT_IMAGE_URL
            vals['image_url'] = image_url
            # Build rich HTML description and technical specs
            if attribute_pairs:
                specs_lines = [
                    f"{name}: {value}"
                    for name, value in attribute_pairs
                    if name and value
                ]
                if specs_lines:
                    vals['specifications'] = '\n'.join(specs_lines)
            
            related_parts = {}
            if isinstance(json_data, dict) and json_data.get('related_parts'):
                related_parts = json_data['related_parts']

            # Collect SEO keywords (PIES descriptions code KEY)
            seo_keywords = []
            pies_data = product_data.get('pies_data') or {}
            pies_descriptions = pies_data.get('descriptions') or []
            for desc in pies_descriptions:
                if desc.get('description_code') == 'KEY' and desc.get('value'):
                    seo_keywords.append(desc.get('value'))
            
            html_description = self._build_html_description(product_data, attribute_pairs, related_parts)
            if html_description:
                vals['long_description'] = html_description
            if seo_keywords:
                vals['seo_keywords'] = ', '.join(seo_keywords)
            
            # Handle inventory and website categories from the API breadcrumbs
            category_vals = self._ensure_categories(product_data)
            vals.update(category_vals)
            
            stock_qty = vals.get('stock_quantity', 0)
            if 'sellable' in product_data:
                vals['sellable'] = bool(product_data['sellable'])
            # Build availability message based on sellable flag and qty
            availability_msg = self._build_availability_message(vals.get('sellable', True), stock_qty)
            if availability_msg:
                vals['availability_message'] = availability_msg
            
            # Set stock status based on quantity
            vals['stock_status'] = 'in_stock' if stock_qty > 0 else 'out_of_stock'

            # Flag the product as best seller when it appears in the API ranking
            best_seller_skus = self._get_best_seller_skus()
            if best_seller_skus is not None:
                vals['best_seller'] = (vals.get('sku') or '').strip() in best_seller_skus
            
            # Check if product already exists
            existing_product = self.search([
                '|',
                ('finditparts_id', '=', vals.get('finditparts_id')),
                ('sku', '=', vals.get('sku'))
            ], limit=1)
            
            # Website categories are replaced as a whole (many2many)
            website_cat_ids = category_vals.get('public_categ_ids', [(6, 0, [])])[0][2]

            if existing_product:
                existing_product.write(vals)
                _logger.info(f"Updated existing product: {existing_product.sku}")
                tag = existing_product._ensure_brand_tag(vals.get('manufacturer'))
                if existing_product.odoo_product_id:
                    template_vals = {}
                    if tag:
                        template_vals['product_tag_ids'] = [(4, tag.id)]
                    if category_vals.get('category_id'):
                        template_vals['categ_id'] = category_vals['category_id']
                    if 'public_categ_ids' in existing_product.odoo_product_id._fields:
                        template_vals['public_categ_ids'] = [(6, 0, website_cat_ids)]
                    template_vals['best_seller'] = existing_product.best_seller
                    if 'sale_delay' in existing_product.odoo_product_id._fields:
                        template_vals['sale_delay'] = (existing_product.estimated_days_to_deliver or 0) + 2
                    if template_vals:
                        existing_product.odoo_product_id.sudo().write(template_vals)
                return existing_product, False
            else:
                new_product = self.create(vals)
                _logger.info(f"Created new product: {new_product.sku}")
                tag = new_product._ensure_brand_tag(vals.get('manufacturer'))
                if new_product.odoo_product_id:
                    template_vals = {}
                    if tag:
                        template_vals['product_tag_ids'] = [(4, tag.id)]
                    if category_vals.get('category_id'):
                        template_vals['categ_id'] = category_vals['category_id']
                    if 'public_categ_ids' in new_product.odoo_product_id._fields:
                        template_vals['public_categ_ids'] = [(6, 0, website_cat_ids)]
                    template_vals['best_seller'] = new_product.best_seller
                    if template_vals:
                        new_product.odoo_product_id.sudo().write(template_vals)
                return new_product, True
                
        except Exception as e:
            _logger.error(f"Failed to create product from JSON: {str(e)}")
            raise
    
    def _fetch_detailed_product_data(self, client, product_data):
        """Fetch a richer product payload (with pies_data/descriptions) when starting
        from a basic /api/v1/products record.

        This is used for search/list endpoints so that we end up with the same
        level of detail as the lookup endpoint.
        """
        product_id = product_data.get('id') or product_data.get('product_id')
        pn = product_data.get('part_number')
        if not product_id and not pn:
            return None
        try:
            detail = None
            if product_id:
                detail = client.get_product_with_pies_data(product_id, include_pies_data=True)
            if not detail and pn:
                detail = client.lookup_product_by_part_number(pn, include_pies_data=True)
            if not detail or not isinstance(detail, dict):
                return None
            return detail
        except Exception as e:
            _logger.warning(f"Failed to enrich product data for {pn or product_id}: {e}")
            return None

    @api.model
    def sync_products_from_api(self, search_query=None, part_number=None, limit=100, config=None):
        """Sync products from FinditParts API and create them in Odoo"""
        config = config or self.env['finditparts.config'].get_active_config()
        if not config:
            raise ValidationError(_('No active FinditParts configuration found'))
        
        from ..utils.api_client import FindinPartAPIClient
        client = FindinPartAPIClient(config)
        
        try:
            # Refresh the API best-seller ranking once per request and flag
            # every matching product already present in Odoo.
            best_seller_skus = self._get_best_seller_skus(client=client, force=True)
            if best_seller_skus is not None:
                self._apply_best_seller_flags(best_seller_skus)

            # Determine source label (for temporary debug marker)
            if part_number:
                source_label = 'lookup'
            elif search_query:
                source_label = 'search'
            else:
                source_label = 'list'

            # Get products from API
            if part_number:
                response = client.lookup_product_by_part_number(part_number, include_pies_data=True)
                products_batches = []
                if response and response.get('errno', 0) == 0 and isinstance(response, dict):
                    # /api/v1/products/lookup may return one of several shapes:
                    # 1) {"errno": 0, "products": [ {"product": {...}, ...}, ...] }
                    # 2) {"errno": 0, "main_part": {...}, "part_number_matches": [...], ...}
                    # 3) {"errno": 0, "part_number_matches": [...], ...}
                    products: list = []
                    resp_products = response.get('products') or []
                    if isinstance(resp_products, list) and resp_products:
                        # Case 1: direct list of product containers
                        products = resp_products
                    elif response.get('main_part'):
                        # Case 2: main_part + matches; let create_from_api_json
                        # decide how to merge main_part and part_number_matches.
                        products = [response]
                    elif isinstance(response.get('part_number_matches'), list) and response.get('part_number_matches'):
                        # Case 3: only matches, no main_part; treat each match as a product
                        products = response['part_number_matches']
                    elif response.get('product'):
                        # Fallback in case the API ever returns a single "product" object
                        products = [response]
                    if products:
                        products_batches = [products]
            elif search_query:
                products_batches = client.search_products_paginated(
                    search_query,
                    strict=False,
                    total_limit=limit,
                    batch_size=min(100, max(1, limit)),
                )
            else:
                products_batches = client.get_products_paginated(
                    total_limit=limit,
                    batch_size=min(100, max(1, limit)),
                )
            
            created_products = []
            updated_products = []
            errors = []
            
            for products in products_batches:
                for product_data in products:
                    print(product_data)
                    try:
                        effective_data = product_data
                        # For search/list results, use a detailed call to fetch
                        # full product information (pies_data, descriptions, etc.).
                        if source_label in ('search', 'list'):
                            enriched = self._fetch_detailed_product_data(client, product_data)
                            if enriched:
                                effective_data = enriched

                        # Create or update product
                        finditparts_product, was_created = self.create_from_api_json(effective_data)
                        
                        # Sync to Odoo if auto_create_products is enabled
                        if config.auto_create_products:
                            sync_result = finditparts_product.sync_to_odoo()
                            if sync_result:
                                if was_created:
                                    if len(created_products) < 200:
                                        created_products.append(finditparts_product)
                                else:
                                    if len(updated_products) < 200:
                                        updated_products.append(finditparts_product)
                            else:
                                errors.append(f"Failed to sync {finditparts_product.sku} to Odoo")
                        
                    except Exception as e:
                        error_msg = f"Failed to process product {product_data.get('part_number', 'Unknown')}: {str(e)}"
                        errors.append(error_msg)
                        _logger.error(error_msg)
            
            # Update config sync date
            config.last_sync_date = fields.Datetime.now()
            config.update_sync_schedule()
            
            return {
                'created': len(created_products),
                'updated': len(updated_products),
                'errors': errors,
                'created_products': created_products,
                'updated_products': updated_products
            }
            
        except Exception as e:
            _logger.error(f"API sync failed: {str(e)}")
            raise ValidationError(_(f"API sync failed: {str(e)}"))
    
    def action_sync_from_api(self):
        """Manual action to sync products from API"""
        wizard = self.env['finditparts.product.sync.wizard'].create({})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finditparts.product.sync.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Sync Products from API')
        }
