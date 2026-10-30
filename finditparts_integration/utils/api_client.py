import requests
import json
import logging
import time
import base64
import hmac
import hashlib
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class FindinPartAPIClient:
    """Client for communicating with FindinPart API"""
    
    def __init__(self, config):
        self.config = config
        base_url = config.api_base_url or 'https://www-build.finditparts.com'
        self.base_url = base_url.rstrip('/')
        self.jwt_issuer = config.jwt_issuer
        self.jwt_secret = config.jwt_secret or '222b6c16-b54a-4ad6-a2c7-e43ba7c23060'
        self.jwt_audience = config.jwt_audience or 'https://api.finditparts.com'
        self.jwt_expiry_hours = config.jwt_expiry_hours
        self.session = requests.Session()
        self.current_token = None
        self.token_expiry = None
        
        # Set default headers (Authorization will be added dynamically)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Odoo-FindinPart-Integration/1.0',
        })
    
    def _generate_jwt_token(self):
        """Generate JWT token for API authentication"""
        try:
            now = int(time.time())
            expiry = now + (self.jwt_expiry_hours * 3600)  # Convert hours to seconds
            
            header = {
                "alg": "HS256",
                "typ": "JWT"
            }
            
            payload = {
                "iss": self.jwt_issuer,           # autohaus-build
                "aud": self.jwt_audience,         # https://api.finditparts.com
                "iat": now,                       # Issued at
                "exp": expiry                     # Expires at
            }
            
            header_encoded = base64.urlsafe_b64encode(
                json.dumps(header, separators=(',', ':')).encode()
            ).decode().rstrip('=')
            
            payload_encoded = base64.urlsafe_b64encode(
                json.dumps(payload, separators=(',', ':')).encode()
            ).decode().rstrip('=')
            
            message = f"{header_encoded}.{payload_encoded}"
            signature = hmac.new(
                self.jwt_secret.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            
            signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip('=')
            
            jwt_token = f"{header_encoded}.{payload_encoded}.{signature_encoded}"
            
            self.current_token = jwt_token
            self.token_expiry = datetime.fromtimestamp(expiry)
            
            _logger.info(f"Generated JWT token, expires at: {self.token_expiry}")
            return jwt_token
            
        except Exception as e:
            _logger.error(f"Failed to generate JWT token: {str(e)}")
            raise Exception(f"JWT token generation failed: {str(e)}")
    
    def _get_valid_token(self):
        """Get a valid JWT token, generating new one if needed"""
        now = datetime.now()
        
        if (self.current_token is None or 
            self.token_expiry is None or 
            now >= self.token_expiry - timedelta(minutes=5)):  # Refresh 5 min before expiry
            
            _logger.info("Generating new JWT token...")
            return self._generate_jwt_token()
        
        return self.current_token
    
    def _make_request(self, method, endpoint, params=None, data=None, timeout=30):
        """Make HTTP request to API"""
        url = f"{self.base_url}{endpoint}"
        
        token = self._get_valid_token()
        self.session.headers['Authorization'] = f'Bearer {token}'
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=timeout)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, json=data, timeout=timeout)
            elif method.upper() == 'PUT':
                response = self.session.put(url, params=params, json=data, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"API request failed: {str(e)}")
            raise Exception(f"API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            _logger.error(f"Failed to parse API response: {str(e)}")
            raise Exception("Failed to parse API response")
    
    def test_connection(self):
        """Test API connection and authentication"""
        try:
            # Use a real public endpoint for reliability across environments
            response = self._make_request('GET', '/api/v1/products', params={'limit': 1})
            return {'success': True, 'data': response}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_products(self, page=1, limit=100, category=None, brand=None, search=None):
        """Get products from API with pagination and filters"""
        params = {
            'page': page,
            'limit': limit,
        }
        
        if category:
            params['category'] = category
        if brand:
            params['brand'] = brand
        if search:
            params['search'] = search
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get products: {str(e)}")
            return None

    def get_best_sellers(self, limit=100, page=1):
        """Get products ordered by best sellers.

        The API exposes the ranking through the ``order`` parameter; there is
        no dedicated endpoint nor sales figures in the payload.
        """
        try:
            return self._make_request(
                'GET',
                '/api/v1/products',
                params={'limit': limit, 'page': page, 'order': 'best_selling'},
            )
        except Exception as e:
            _logger.error(f"Failed to get best sellers: {str(e)}")
            return None

    def get_products_paginated(self, total_limit=50000, batch_size=100):
        """Generator: paginate basic product list until total_limit or last page"""
        fetched = 0
        page = 1
        while fetched < total_limit:
            try:
                remaining = total_limit - fetched
                limit = batch_size if remaining > batch_size else remaining
                resp = self.get_products(page=page, limit=limit)
                if not resp or 'products' not in resp:
                    break
                products = resp.get('products', [])
                if not products:
                    break
                yield products
                fetched += len(products)
                pagination = resp.get('pagination', {})
                current_page = pagination.get('current_page', page)
                total_pages = pagination.get('total_pages')
                if total_pages and current_page >= total_pages:
                    break
                page += 1
            except Exception as e:
                _logger.warning(f"Pagination interrupted on page {page}: {e}")
                break
    
    def get_product_by_sku(self, sku):
        """Get specific product by SKU"""
        try:
            response = self._make_request('GET', f'/api/v1/products/{sku}')
            return response
        except Exception as e:
            _logger.error(f"Failed to get product {sku}: {str(e)}")
            return None
    
    def search_products_with_query(self, query, strict=True, limit=100, page=1):
        """Search products with query string and strict mode
        Example: /api/v1/products?q=brake&strict=true&limit=100&page=1
        """
        params = {'q': query, 'limit': limit, 'page': page}
        if strict:
            params['strict'] = 'true'
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to search products with query '{query}': {str(e)}")
            return None

    def search_products_paginated(self, query, strict=True, total_limit=50000, batch_size=100):
        """Generator: paginate search results until total_limit or last page"""
        fetched = 0
        page = 1
        while fetched < total_limit:
            try:
                remaining = total_limit - fetched
                limit = batch_size if remaining > batch_size else remaining
                resp = self.search_products_with_query(query, strict=strict, limit=limit, page=page)
                if not resp or 'products' not in resp:
                    break
                products = resp.get('products', [])
                if not products:
                    break
                yield products
                fetched += len(products)
                pagination = resp.get('pagination', {})
                current_page = pagination.get('current_page', page)
                total_pages = pagination.get('total_pages')
                if total_pages and current_page >= total_pages:
                    break
                page += 1
            except Exception as e:
                _logger.warning(f"Pagination interrupted on page {page}: {e}")
                break
    
    def search_products_by_part_number(self, part_number, strict=True):
        """Search products by part number with strict mode
        Example: /api/v1/products?strict=true&pn=5280X
        """
        params = {'pn': part_number}
        if strict:
            params['strict'] = 'true'
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to search products by part number '{part_number}': {str(e)}")
            return None
    
    def search_products_v3(self, part_number, eoos=True, aggs=True):
        """Search products using v3 search engine
        Example: /api/v1/products?use_v3_search=true&part_number=DR10511414&eoos=true&aggs=true
        """
        params = {
            'use_v3_search': 'true',
            'part_number': part_number
        }
        if eoos:
            params['eoos'] = 'true'
        if aggs:
            params['aggs'] = 'true'
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to search products v3 with part number '{part_number}': {str(e)}")
            return None
    
    def search_products_with_aggregations(self, query, aggs=True, order=None):
        """Search products with aggregations and ordering
        Example: /api/v1/products?q=haldex KN20001&aggs=true&order=price_to_high
        """
        params = {'q': query}
        if aggs:
            params['aggs'] = 'true'
        if order:
            params['order'] = order
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to search products with aggregations '{query}': {str(e)}")
            return None
    
    def lookup_product_by_part_number(self, part_number, include_pies_data=True):
        """Lookup product by part number with PIES data
        Example: /api/v1/products/lookup?part_number=WL10179&include_pies_data=true
        """
        params = {'part_number': part_number}
        if include_pies_data:
            params['include_pies_data'] = 'true'
        
        try:
            response = self._make_request('GET', '/api/v1/products/lookup', params=params)
            return response
        except Exception as e:
            if include_pies_data:
                _logger.warning(
                    "Lookup with PIES data failed for part number '%s'; "
                    "retrying without PIES data: %s",
                    part_number,
                    str(e),
                )
                try:
                    response = self._make_request(
                        'GET',
                        '/api/v1/products/lookup',
                        params={'part_number': part_number},
                    )
                    return response
                except Exception as retry_error:
                    _logger.error(
                        "Failed to lookup product by part number '%s' without PIES data: %s",
                        part_number,
                        str(retry_error),
                    )
                    return None
            _logger.error(f"Failed to lookup product by part number '{part_number}': {str(e)}")
            return None
    
    def get_multiple_products(self, product_ids):
        """Get multiple products by their IDs
        Example: /api/v1/products/:product_ids/multi
        """
        if isinstance(product_ids, list):
            product_ids_str = ','.join(map(str, product_ids))
        else:
            product_ids_str = str(product_ids)
        
        try:
            response = self._make_request('GET', f'/api/v1/products/{product_ids_str}/multi')
            return response
        except Exception as e:
            _logger.error(f"Failed to get multiple products {product_ids}: {str(e)}")
            return None
    
    def get_product_with_pies_data(self, product_id, include_pies_data=True):
        """Get product by ID with PIES data
        Example: /api/v1/products/1062657?include_pies_data=true
        """
        params = {}
        if include_pies_data:
            params['include_pies_data'] = 'true'
        
        try:
            response = self._make_request('GET', f'/api/v1/products/{product_id}', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get product {product_id} with PIES data: {str(e)}")
            return None
    
    def get_products_by_pies_category(self, category, page=1, limit=100):
        """Get products by PIES category
        Example: Electrical, Lighting and Body, Brake, etc.
        """
        params = {
            'page': page,
            'limit': limit,
            'pies_category': category
        }
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get products by PIES category '{category}': {str(e)}")
            return None
    
    def get_products_by_pies_subcategory(self, subcategory, page=1, limit=100):
        """Get products by PIES subcategory
        Example: Lighting - Exterior, Hardware, Fasteners and Fittings, etc.
        """
        params = {
            'page': page,
            'limit': limit,
            'pies_subcategory': subcategory
        }
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get products by PIES subcategory '{subcategory}': {str(e)}")
            return None
    
    def get_products_by_category_taxon(self, category_depth, category_name, page=1, limit=100):
        """Get products by category taxon (depth 1, 2, or 3)
        Example: Heavy Duty Truck, Lighting, Signal Lighting, etc.
        """
        params = {
            'page': page,
            'limit': limit,
            f'category_taxon_depth_{category_depth}': category_name
        }
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get products by category taxon depth {category_depth} '{category_name}': {str(e)}")
            return None
    
    def get_products_by_manufacturer(self, manufacturer, page=1, limit=100):
        """Get products by manufacturer
        Example: UNITED PACIFIC, DORMAN, WORLD AMERICAN, etc.
        """
        params = {
            'page': page,
            'limit': limit,
            'manufacturer': manufacturer
        }
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get products by manufacturer '{manufacturer}': {str(e)}")
            return None
    
    def get_all_products_by_category(self, category_type, category_name, batch_size=100):
        """Get ALL products from a specific category using pagination
        Returns a generator that yields batches of products
        """
        page = 1
        total_products = 0
        
        while True:
            if category_type == 'pies_category':
                response = self.get_products_by_pies_category(category_name, page=page, limit=batch_size)
            elif category_type == 'pies_subcategory':
                response = self.get_products_by_pies_subcategory(category_name, page=page, limit=batch_size)
            elif category_type.startswith('category_taxon_depth_'):
                depth = int(category_type.split('_')[-1])
                response = self.get_products_by_category_taxon(depth, category_name, page=page, limit=batch_size)
            elif category_type == 'manufacturer':
                response = self.get_products_by_manufacturer(category_name, page=page, limit=batch_size)
            else:
                _logger.error(f"Unknown category type: {category_type}")
                break
            
            if not response or 'products' not in response:
                break
            
            products = response['products']
            if not products:
                break
            
            total_products += len(products)
            _logger.info(f"Retrieved {len(products)} products from page {page} (total: {total_products})")
            
            yield products
            
            # Check if we've reached the last page
            pagination = response.get('pagination', {})
            current_page = pagination.get('current_page', page)
            per_page = pagination.get('per_page', batch_size)
            total_pages = pagination.get('total_pages', 1)
            
            if current_page >= total_pages:
                break
            
            page += 1
    
    def get_category_aggregations(self):
        """Get all available categories from aggregations"""
        try:
            response = self._make_request('GET', '/api/v1/products', params={'aggs': 'true', 'limit': 1})
            return response.get('aggs', {})
        except Exception as e:
            _logger.error(f"Failed to get category aggregations: {str(e)}")
            return {}
    
    def sync_all_products_by_brand(self, brand_name, batch_size=100):
        """Sync ALL products from a specific brand with full pagination
        This method handles large datasets by yielding batches of products
        """
        page = 1
        total_synced = 0
        
        _logger.info(f"Starting full sync for brand: {brand_name}")
        
        while True:
            try:
                response = self._make_request('GET', '/api/v1/products', 
                                            params={
                                                'manufacturer': brand_name,
                                                'page': page,
                                                'limit': batch_size
                                            })
                
                if not response or 'products' not in response:
                    _logger.warning(f"No response or products for {brand_name} page {page}")
                    break
                
                products = response['products']
                if not products:
                    _logger.info(f"No more products found for {brand_name} at page {page}")
                    break
                
                # Filter out test products if they have specific patterns
                real_products = []
                for product in products:
                    part_number = product.get('part_number', '')
                    description = product.get('short_description', '')
                    manufacturer = product.get('manufacturer', '')
                    
                    # Skip obvious test products
                    if ('test' in description.lower() or 
                        'tkpro' in part_number.lower() or 
                        manufacturer != brand_name):
                        continue
                    
                    real_products.append(product)
                
                if real_products:
                    total_synced += len(real_products)
                    _logger.info(f"Page {page}: Found {len(real_products)} real products for {brand_name} (total: {total_synced})")
                    yield real_products
                else:
                    _logger.info(f"Page {page}: No real products found for {brand_name}, skipping")
                
                # Check pagination
                pagination = response.get('pagination', {})
                current_page = pagination.get('current_page', page)
                total_pages = pagination.get('total_pages', 1)
                
                if current_page >= total_pages:
                    break
                
                page += 1
                
            except Exception as e:
                _logger.error(f"Error syncing {brand_name} page {page}: {str(e)}")
                break
        
        _logger.info(f"Completed sync for {brand_name}: {total_synced} products total")
    
    def get_client_main_brands_products(self, batch_size=50):
        """Get products from the 4 main client brands: CATERPILLAR, CUMMINS, DETROIT, INTERNATIONAL"""
        main_brands = ['CATERPILLAR', 'CUMMINS', 'DETROIT', 'INTERNATIONAL']
        
        # Also try alternative names
        brand_alternatives = {
            'CATERPILLAR': ['CATERPILLAR', 'CAT', 'CATERPILLAR-REPLACEMENT'],
            'CUMMINS': ['CUMMINS', 'CUMMINS-REPLACEMENT'],
            'DETROIT': ['DETROIT', 'DETROIT DIESEL', 'DETROIT-REPLACEMENT'],
            'INTERNATIONAL': ['INTERNATIONAL', 'NAVISTAR', 'INTERNATIONAL-REPLACEMENT']
        }
        
        results = {}
        
        for main_brand in main_brands:
            _logger.info(f"Starting sync for main brand: {main_brand}")
            brand_products = []
            
            # Try different name variations
            for brand_variation in brand_alternatives[main_brand]:
                _logger.info(f"Trying brand variation: {brand_variation}")
                
                try:
                    for product_batch in self.sync_all_products_by_brand(brand_variation, batch_size):
                        brand_products.extend(product_batch)
                        
                        # Yield results as we get them
                        yield {
                            'main_brand': main_brand,
                            'api_brand': brand_variation,
                            'products': product_batch,
                            'batch_total': len(product_batch)
                        }
                        
                except Exception as e:
                    _logger.error(f"Error getting products for {brand_variation}: {str(e)}")
                    continue
            
            results[main_brand] = {
                'total_products': len(brand_products),
                'products': brand_products
            }
            
            _logger.info(f"Completed {main_brand}: {len(brand_products)} total products")
        
        return results
    
    def search_products_by_brand_keyword(self, brand_keyword, limit=100):
        """Search products using brand keyword in search query"""
        try:
            response = self._make_request('GET', '/api/v1/products', 
                                        params={
                                            'q': brand_keyword,
                                            'limit': limit,
                                            'strict': 'false'  # Allow broader matching
                                        })
            return response
        except Exception as e:
            _logger.error(f"Failed to search products by brand keyword '{brand_keyword}': {str(e)}")
            return None
    
    def get_product_stock(self, sku):
        """Get current stock level for a product"""
        try:
            response = self._make_request('GET', f'/products/{sku}/stock')
            return response
        except Exception as e:
            _logger.error(f"Failed to get stock for {sku}: {str(e)}")
            return None
    
    def get_product_pricing(self, sku):
        """Get current pricing for a product"""
        try:
            response = self._make_request('GET', f'/products/{sku}/pricing')
            return response
        except Exception as e:
            _logger.error(f"Failed to get pricing for {sku}: {str(e)}")
            return None
    
    def get_categories(self):
        """Get all available product categories"""
        try:
            response = self._make_request('GET', '/categories')
            return response
        except Exception as e:
            _logger.error(f"Failed to get categories: {str(e)}")
            return None
    
    def get_brands(self):
        """Get all available brands"""
        try:
            response = self._make_request('GET', '/brands')
            return response
        except Exception as e:
            _logger.error(f"Failed to get brands: {str(e)}")
            return None
    
    def create_order(self, order_data):
        """Create a new order in FindinPart"""
        try:
            response = self._make_request('POST', '/orders', data=order_data)
            return response
        except Exception as e:
            _logger.error(f"Failed to create order: {str(e)}")
            return None
    
    def get_order_status(self, order_id):
        """Get status of an existing order"""
        try:
            response = self._make_request('GET', f'/orders/{order_id}')
            return response
        except Exception as e:
            _logger.error(f"Failed to get order status {order_id}: {str(e)}")
            return None
    
    def update_order(self, order_id, update_data):
        """Update an existing order"""
        try:
            response = self._make_request('PUT', f'/orders/{order_id}', data=update_data)
            return response
        except Exception as e:
            _logger.error(f"Failed to update order {order_id}: {str(e)}")
            return None
    
    def cancel_order(self, order_id, reason=None):
        """Cancel an existing order"""
        data = {'status': 'cancelled'}
        if reason:
            data['cancellation_reason'] = reason
        
        try:
            response = self._make_request('PUT', f'/orders/{order_id}', data=data)
            return response
        except Exception as e:
            _logger.error(f"Failed to cancel order {order_id}: {str(e)}")
            return None
    
    def get_order_tracking(self, order_id):
        """Get tracking information for an order"""
        try:
            response = self._make_request('GET', f'/orders/{order_id}/tracking')
            return response
        except Exception as e:
            _logger.error(f"Failed to get tracking for order {order_id}: {str(e)}")
            return None

    def _create_cart(self):
        """Create a new FinditParts cart and return its dict (id + token)."""
        response = self._make_request('POST', '/api/v1/carts', data={})
        if not isinstance(response, dict):
            return None
        cart = response.get('cart') or response.get('data') or {}
        if not isinstance(cart, dict):
            cart = response
        return cart if cart.get('id') else None

    def _cart_params(self, cart):
        cart_token = cart.get('cart_token') if isinstance(cart, dict) else None
        return {'token': cart_token} if cart_token else None

    def _add_cart_line_item(self, cart, item):
        cart_id = cart.get('id')
        params = self._cart_params(cart)
        payload = {
            'product_id': item.get('product_id'),
            'quantity': item.get('quantity') or 1,
        }
        if item.get('variant_id'):
            payload['variant_id'] = item.get('variant_id')
        return self._make_request(
            'POST',
            f'/api/v1/carts/{cart_id}/line_items',
            params=params,
            data=payload,
        )

    def _set_cart_shipping_address(self, cart, shipping_address):
        cart_id = cart.get('id')
        params = self._cart_params(cart)
        return self._make_request(
            'PUT',
            f'/api/v1/carts/{cart_id}/shipping_address',
            params=params,
            data={'address': shipping_address},
        )

    def _get_cart_shipping_methods(self, cart):
        cart_id = cart.get('id')
        params = self._cart_params(cart)
        return self._make_request(
            'GET',
            f'/api/v1/carts/{cart_id}/shipping_methods',
            params=params,
        )

    @staticmethod
    def _normalize_shipping_methods(response):
        """Normalize the /shipping_methods response into rate dictionaries.

        The provider's exact shape is confirmed through the cart flow. This
        parser is defensive and accepts the common wrappers and field names so
        it degrades to an empty list (pending quote) instead of crashing.
        """
        if isinstance(response, dict):
            raw_methods = (
                response.get('shipping_methods')
                or response.get('methods')
                or response.get('rates')
                or response.get('shipping_rates')
                or response.get('data')
            )
            if raw_methods is None and 'id' not in response:
                raw_methods = [response]
        elif isinstance(response, list):
            raw_methods = response
        else:
            raw_methods = []

        normalized = []
        for raw in raw_methods or []:
            if not isinstance(raw, dict):
                continue
            base_rate = (
                raw.get('amount_without_promo')
                or raw.get('amount')
                or raw.get('price')
                or raw.get('rate')
                or raw.get('cost')
                or raw.get('total')
                or raw.get('base_rate')
                or raw.get('shipping_amount')
            )
            if base_rate is None:
                continue
            try:
                base_rate = float(base_rate)
            except (TypeError, ValueError):
                continue
            normalized.append({
                'service': (
                    raw.get('carrier_type')
                    or raw.get('service')
                    or raw.get('service_code')
                    or raw.get('carrier')
                    or raw.get('name')
                    or ''
                ),
                'label': raw.get('label') or '',
                'base_rate': base_rate,
                'currency': raw.get('currency') or 'USD',
                'transit': raw.get('days_to_deliver') or raw.get('estimated_days') or '',
                'eligible': bool(raw.get('available', raw.get('eligible', True))),
            })
        return normalized

    def get_shipping_rates(self, dest_country, dest_zip=None, cart_items=None,
                           service_types=None, weight=None):
        """Get shipping rates reported by FinditParts for a destination.

        This drives the real cart flow: create a cart, add the line items, set
        a US shipping address and read the domestic US shipping methods. The
        ``cart_items`` must be a list of dicts with ``product_id`` (the
        FinditParts product id) and optionally ``variant_id``. When the API is
        unavailable or returns no valid rates, an empty list is returned so the
        caller can fall back to the weight-only markup.
        weight-only markup.

        Returns a list of normalized rate dictionaries:
            [{'service': 'ground', 'base_rate': 18.0, 'currency': 'USD',
              'transit': '6-7', 'eligible': True}, ...]
        """
        items = cart_items or []
        if not items or dest_country != 'US':
            return []

        try:
            cart = self._create_cart()
            if not cart:
                return []
            for item in items:
                self._add_cart_line_item(cart, item)
            shipping_address = self._us_shipping_address(dest_zip)
            if shipping_address:
                self._set_cart_shipping_address(cart, shipping_address)
            response = self._get_cart_shipping_methods(cart)
        except Exception as e:
            _logger.info(
                "FinditParts shipping rates unavailable for %s: %s",
                dest_country, str(e),
            )
            return []

        return self._normalize_shipping_methods(response)

    @staticmethod
    def _us_shipping_address(dest_zip=None):
        """Return the default US warehouse shipping address for rate quoting."""
        return {
            'first_name': 'Warehouse',
            'last_name': 'Pickup',
            'address1': '123 Warehouse St',
            'city': 'Miami',
            'state': 'FL',
            'zipcode': dest_zip or '33101',
            'country': 'US',
            'phone': '5551234567',
        }


    def search_products(self, query, filters=None, page=1, limit=100):
        """Search products with advanced filters"""
        params = {
            'q': query,
            'page': page,
            'limit': limit,
        }
        
        if filters:
            params.update(filters)
        
        try:
            response = self._make_request('GET', '/api/v1/products', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to search products: {str(e)}")
            return None
    
    def get_product_images(self, sku):
        """Get all images for a specific product"""
        try:
            response = self._make_request('GET', f'/products/{sku}/images')
            return response
        except Exception as e:
            _logger.error(f"Failed to get images for {sku}: {str(e)}")
            return None
    
    def get_inventory_updates(self, since_date=None):
        """Get inventory updates since a specific date"""
        params = {}
        if since_date:
            if isinstance(since_date, datetime):
                params['since'] = since_date.isoformat()
            else:
                params['since'] = since_date
        
        try:
            response = self._make_request('GET', '/inventory/updates', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get inventory updates: {str(e)}")
            return None
    
    def get_pricing_updates(self, since_date=None):
        """Get pricing updates since a specific date"""
        params = {}
        if since_date:
            if isinstance(since_date, datetime):
                params['since'] = since_date.isoformat()
            else:
                params['since'] = since_date
        
        try:
            response = self._make_request('GET', '/pricing/updates', params=params)
            return response
        except Exception as e:
            _logger.error(f"Failed to get pricing updates: {str(e)}")
            return None
    
    def validate_product_data(self, product_data):
        """Validate product data before sending to API"""
        required_fields = ['sku', 'name', 'description']
        missing_fields = [field for field in required_fields if not product_data.get(field)]
        
        if missing_fields:
            raise Exception(f"Missing required fields: {', '.join(missing_fields)}")
        
        numeric_fields = ['price', 'cost', 'weight', 'stock']
        for field in numeric_fields:
            if field in product_data and product_data[field] is not None:
                try:
                    float(product_data[field])
                except (ValueError, TypeError):
                    raise Exception(f"Field {field} must be a valid number")
        
        return True
