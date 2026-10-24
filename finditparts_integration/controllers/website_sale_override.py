from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request
import json
import logging
import re
import time

_logger = logging.getLogger(__name__)


class WebsiteSalePickup(WebsiteSale):
    """
    Capture the warehouse_selection field on checkout address submission and
    persist it on the current sale order.
    """

    _PART_NUMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,39}$")
    _PART_NUMBER_LOOKUP_TTL = 600

    @http.route('/shop/autocomplete', type='http', auth='public', website=True,
                methods=['GET'], csrf=False)
    def shop_autocomplete(self, q='', limit=8, **kwargs):
        """Return lightweight public product suggestions for the header search."""
        query = (q or '').strip()
        try:
            limit = min(max(int(limit), 1), 12)
        except (TypeError, ValueError):
            limit = 8

        if len(query) < 2:
            return request.make_json_response({'results': []})

        Product = request.env['product.template'].sudo()
        domain = [
            ('sale_ok', '=', True),
            '|', ('name', 'ilike', query),
            ('default_code', 'ilike', query),
        ]
        if 'is_published' in Product._fields:
            domain.insert(0, ('is_published', '=', True))
        products = Product.search(domain, limit=limit)

        # A part number is also stored in finditparts.product, so include linked
        # products when the match is not in the native product name/SKU.
        if len(products) < limit:
            linked = request.env['finditparts.product'].sudo().search([
                '|', ('sku', 'ilike', query), ('part_number', 'ilike', query),
            ], limit=limit)
            linked_products = linked.mapped('odoo_product_id').filtered(
                lambda product: product.sale_ok and (
                    'is_published' not in product._fields or product.is_published
                )
            )
            products |= linked_products

        results = []
        for product in products[:limit]:
            results.append({
                'id': product.id,
                'name': product.name,
                'sku': product.default_code or '',
                'url': product.website_url or '/shop?search=%s' % query,
                'image': '/web/image/product.template/%s/image_128' % product.id,
            })
        return request.make_json_response({'results': results})

    def _looks_like_part_number(self, search):
        search = (search or "").strip()
        return bool(
            search
            and self._PART_NUMBER_RE.match(search)
            and any(char.isdigit() for char in search)
        )

    def _has_local_part_number(self, products, search):
        search = (search or "").strip().casefold()
        if not search:
            return False
        return any(
            (product.finditparts_part_number or product.default_code or "").strip().casefold()
            == search
            for product in products
        )

    def _lookup_part_number_from_api(self, part_number):
        lookups = request.session.get("autohaus_part_lookups") or {}
        now = time.time()
        last_lookup = lookups.get(part_number)
        if last_lookup and now - last_lookup < self._PART_NUMBER_LOOKUP_TTL:
            return True

        config = request.env["finditparts.config"].sudo().get_active_config()
        if not config or not config.auto_create_products:
            return False

        result = request.env["finditparts.product"].sudo().sync_products_from_api(
            part_number=part_number,
            limit=1,
        )
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        _logger.info(
            "On-demand FinditParts lookup for %s: %s created, %s updated",
            part_number,
            created,
            updated,
        )

        imported = bool(created or updated)
        if imported:
            lookups = {
                key: value
                for key, value in lookups.items()
                if now - value < self._PART_NUMBER_LOOKUP_TTL
            }
            lookups[part_number] = now
            request.session["autohaus_part_lookups"] = lookups
        return imported

    def _shop_lookup_products(self, options, post, search, website):
        result = super()._shop_lookup_products(options, post, search, website)

        if not self._looks_like_part_number(search):
            return result
        if self._has_local_part_number(result[2], search):
            return result
        try:
            imported = self._lookup_part_number_from_api(search.strip())
        except Exception:
            _logger.exception(
                "FinditParts on-demand lookup failed for part number %s",
                search,
            )
            return result
        if not imported:
            return result

        return super()._shop_lookup_products(options, post, search, website)

    def _current_order(self):
        order_id = request.session.get("sale_order_id")
        if not order_id:
            return False
        order = request.env["sale.order"].sudo().browse(order_id)
        return order.exists()

    def checkout_form_save(self, mode, checkout, all_values):
        # Capture warehouse selection from form submission
        warehouse_code = all_values.get("warehouse_selection") or request.params.get("warehouse_selection")
        partner_id = super().checkout_form_save(mode, checkout, all_values)

        order = self._current_order()
        if warehouse_code and order:
            order.sudo().write({"pickup_warehouse": warehouse_code})
            # Update partner name only if it is empty or a generic placeholder
            if partner_id:
                partner = request.env["res.partner"].sudo().browse(partner_id)
                warehouse_name = "USA Warehouse" if warehouse_code == "usa" else "Panama Warehouse"
                if not partner.name or partner.name in ("", "Warehouse Pickup", "Public user"):
                    partner.write({"name": warehouse_name})
        return partner_id

    @http.route("/shop/pickup/set", type="json", auth="public", website=True, csrf=False)
    def shop_pickup_set(self, warehouse=None, **kwargs):
        """
        Persist the pickup warehouse on the current sale order from the frontend JS.
        """
        try:
            if isinstance(warehouse, str):
                pass
            elif warehouse is None and request.httprequest.data:
                payload = json.loads(request.httprequest.data.decode("utf-8") or "{}")
                warehouse = payload.get("warehouse")
            order = self._current_order()
            if order and warehouse in ("usa", "panama"):
                order.sudo().write({"pickup_warehouse": warehouse})
                return {"status": "ok", "pickup_warehouse": warehouse}
        except Exception:
            return {"status": "error"}
        return {"status": "noop"}

    @http.route("/shop/pickup/info", type="json", auth="public", website=True, csrf=False)
    def shop_pickup_info(self, **kwargs):
        """Small debug helper to inspect current order and shipping partner."""
        order = self._current_order()
        if not order:
            return {"status": "noop"}
        partner = order.partner_shipping_id
        return {
            "status": "ok",
            "order_id": order.id,
            "pickup_warehouse": order.pickup_warehouse,
            "partner_shipping_id": partner.id,
            "partner_shipping_name": partner.name,
            "partner_shipping_street": partner.street,
            "partner_shipping_city": partner.city,
            "partner_shipping_zip": partner.zip,
            "partner_shipping_country": partner.country_id.name,
        }
