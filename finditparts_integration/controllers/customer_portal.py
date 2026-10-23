from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound


class CustomerPortal(http.Controller):
    def _partner(self):
        if request.env.user._is_public():
            return None
        return request.env.user.partner_id.commercial_partner_id

    def _order(self, order_id):
        partner = self._partner()
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if not partner or not order:
            raise NotFound()
        if order.partner_id.commercial_partner_id != partner:
            raise Forbidden()
        return order

    @http.route("/my", type="http", auth="user", website=True)
    def account_alias(self, **kwargs):
        """Use the Autohaus account dashboard as the customer's portal home."""
        return request.redirect("/mi-cuenta")

    @http.route("/mi-cuenta", type="http", auth="user", website=True)
    def account_home(self, **kwargs):
        partner = self._partner()
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "child_of", partner.id)], order="date_order desc, id desc", limit=5
        )
        invoices = request.env["account.move"].sudo().search(
            [("partner_id", "child_of", partner.id), ("move_type", "in", ("out_invoice", "out_refund"))],
            order="invoice_date desc, id desc", limit=5
        )
        requests = request.env["finditparts.customer.request"].sudo().search(
            [("partner_id", "=", partner.id)], limit=5
        )
        return request.render("finditparts_integration.customer_account_home", {
            "partner": partner, "orders": orders, "invoices": invoices, "requests": requests,
        })

    @http.route("/mi-cuenta/pedidos", type="http", auth="user", website=True)
    def orders(self, **kwargs):
        partner = self._partner()
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "child_of", partner.id)], order="date_order desc, id desc"
        )
        return request.render("finditparts_integration.customer_orders", {"orders": orders})

    @http.route("/mi-cuenta/pedido/<int:order_id>", type="http", auth="user", website=True)
    def order_detail(self, order_id, **kwargs):
        order = self._order(order_id)
        return request.render("finditparts_integration.customer_order_detail", {"order": order})

    @http.route("/mi-cuenta/facturas", type="http", auth="user", website=True)
    def invoices(self, **kwargs):
        partner = self._partner()
        moves = request.env["account.move"].sudo().search(
            [("partner_id", "child_of", partner.id), ("move_type", "in", ("out_invoice", "out_refund"))],
            order="invoice_date desc, id desc"
        )
        return request.render("finditparts_integration.customer_invoices", {"invoices": moves})

    @http.route("/mi-cuenta/factura/<int:move_id>/pdf", type="http", auth="user", website=True)
    def invoice_pdf(self, move_id, **kwargs):
        partner = self._partner()
        move = request.env["account.move"].sudo().browse(move_id).exists()
        if not move or move.partner_id.commercial_partner_id != partner:
            raise Forbidden()
        return request.redirect("/my/invoices/%s?report_type=pdf" % move.id)

    @http.route("/mi-cuenta/cotizaciones", type="http", auth="user", website=True)
    def quotations(self, **kwargs):
        partner = self._partner()
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "child_of", partner.id), ("state", "in", ("draft", "sent"))],
            order="date_order desc, id desc"
        )
        return request.render("finditparts_integration.customer_quotations", {"orders": orders})

    @http.route("/mi-cuenta/solicitudes", type="http", auth="user", website=True)
    def requests(self, **kwargs):
        partner = self._partner()
        records = request.env["finditparts.customer.request"].sudo().search(
            [("partner_id", "=", partner.id)]
        )
        return request.render("finditparts_integration.customer_requests", {"requests": records})

    @http.route("/mi-cuenta/solicitud", type="http", auth="user", website=True, methods=["GET", "POST"])
    def request_create(self, **post):
        partner = self._partner()
        error = None
        if request.httprequest.method == "POST":
            if not post.get("reason") or not post.get("description"):
                error = "Indica el motivo y una descripción."
            else:
                order = self._order(int(post["order_id"])) if post.get("order_id") else False
                request.env["finditparts.customer.request"].sudo().create({
                    "partner_id": partner.id,
                    "sale_order_id": order.id if order else False,
                    "request_type": post.get("request_type", "return"),
                    "reason": post["reason"],
                    "description": post["description"],
                })
                return request.redirect("/mi-cuenta/solicitudes")
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "child_of", partner.id)], order="date_order desc"
        )
        return request.render("finditparts_integration.customer_request_form", {"orders": orders, "error": error})

    @http.route("/mi-cuenta/volver-a-comprar/<int:line_id>", type="http", auth="user", website=True)
    def reorder(self, line_id, **kwargs):
        partner = self._partner()
        line = request.env["sale.order.line"].sudo().browse(line_id).exists()
        if not line or line.order_id.partner_id.commercial_partner_id != partner:
            raise Forbidden()
        order = request.website.sale_get_order(force_create=True)
        order._cart_update(product_id=line.product_id.id, add_qty=line.product_uom_qty or 1)
        return request.redirect("/shop/cart")
