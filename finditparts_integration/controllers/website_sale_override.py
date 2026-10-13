from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request
import json


class WebsiteSalePickup(WebsiteSale):
    """
    Capture the warehouse_selection field on checkout address submission and
    persist it on the current sale order.
    """

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
