import hashlib
import logging
from datetime import timedelta

from odoo import api, fields, models

from .delivery_carrier import PANAMA_AIR_SERVICES, PANAMA_SERVICE_DEFS

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pickup_warehouse = fields.Selection(
        selection=[
            ("usa", "USA Warehouse"),
            ("panama", "Panama Warehouse"),
        ],
        string="Pickup Warehouse",
        help="Warehouse selected by the customer at checkout (USA or Panama).",
    )

    tracking_state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("processing_usa", "Procesando en Estados Unidos"),
            ("in_transit", "En tránsito a Panamá"),
            ("panama_customs", "En aduanas de Panamá"),
            ("ready_panama", "Listo en Panamá"),
            ("delivered", "Entregado"),
        ],
        string="Estado de seguimiento",
        default="pending",
        copy=False,
    )
    tracking_number = fields.Char(string="Número de seguimiento", copy=False)
    logistics_actual_cost = fields.Monetary(
        string="Costo real de envío",
        currency_field="currency_id",
        copy=False,
        help=(
            "Costo efectivamente pagado al transportista, tomado de la factura, "
            "guía o cotización real del envío."
        ),
    )
    logistics_charged_amount = fields.Monetary(
        string="Envío cobrado al cliente",
        currency_field="currency_id",
        compute="_compute_logistics_costs",
        store=True,
        readonly=True,
    )
    logistics_result = fields.Monetary(
        string="Resultado del envío",
        currency_field="currency_id",
        compute="_compute_logistics_costs",
        store=True,
        readonly=True,
        help="Importe cobrado al cliente menos el costo real del envío.",
    )
    logistics_loss = fields.Boolean(
        string="Pérdida logística",
        compute="_compute_logistics_costs",
        store=True,
        readonly=True,
        help="Se activa cuando el costo real del envío supera lo cobrado al cliente.",
    )
    estimated_delivery_miami = fields.Date(
        string="Entrega estimada Miami", compute="_compute_delivery_dates", store=True
    )
    estimated_delivery_panama = fields.Date(
        string="Entrega estimada Panamá", compute="_compute_delivery_dates", store=True
    )
    logistics_usa_base_rate = fields.Float(
        string="Tarifa base USA cacheada",
        digits=(10, 2),
        readonly=True,
        copy=False,
        help=(
            "Tarifa de envío doméstico dentro de Estados Unidos reportada por "
            "FinditParts para el contenido actual del pedido. Se recalcula solo "
            "cuando cambian las líneas o el almacén de recogida."
        ),
    )
    logistics_usa_base_rate_hash = fields.Char(
        string="Hash de tarifa base USA",
        compute="_compute_logistics_usa_base_rate_hash",
        store=True,
        readonly=True,
    )

    @api.depends("date_order", "commitment_date", "order_line.customer_lead", "pickup_warehouse")
    def _compute_delivery_dates(self):
        """Compute a base Miami date and add exactly two days for Panama."""
        for order in self:
            base_date = fields.Date.to_date(order.commitment_date or order.date_order)
            if not base_date:
                order.estimated_delivery_miami = False
                order.estimated_delivery_panama = False
                continue
            transit_days = max(order.order_line.mapped("customer_lead") or [0])
            miami_date = base_date + timedelta(days=int(transit_days))
            order.estimated_delivery_miami = miami_date
            order.estimated_delivery_panama = miami_date + timedelta(days=2)

    @api.depends(
        "order_line.is_delivery",
        "order_line.price_subtotal",
        "logistics_actual_cost",
    )
    def _compute_logistics_costs(self):
        for order in self:
            charged = sum(
                order.order_line.filtered("is_delivery").mapped("price_subtotal")
            )
            order.logistics_charged_amount = charged
            order.logistics_result = charged - order.logistics_actual_cost
            order.logistics_loss = bool(
                order.logistics_actual_cost and order.logistics_actual_cost > charged
            )

    def get_portal_tracking(self):
        self.ensure_one()
        state = self.tracking_state or "pending"
        if state == "pending" and self.state == "sale":
            state = "processing_usa"
        elif self.state == "done":
            state = "delivered"
        state_labels = dict(self._fields["tracking_state"].selection)
        return {
            "state": state,
            "state_label": state_labels.get(state, "Pendiente"),
            "warehouse": self.pickup_warehouse or "usa",
            "tracking_number": self.tracking_number,
            "miami_date": self.estimated_delivery_miami,
            "panama_date": self.estimated_delivery_panama,
        }

    # ----------------------------------------------------------------------
    # Autohaus shipping quoting engine (weight-only, no dimensions from API)
    # ----------------------------------------------------------------------

    def _autohaus_config(self):
        """Return the active FinditParts config (internal, sudo)."""
        return self.env["finditparts.config"].sudo().get_active_config()

    def _autohaus_markup_per_lb(self):
        config = self._autohaus_config()
        if config:
            return config.panama_markup_per_lb
        param = self.env["ir.config_parameter"].sudo().get_param(
            "autohaus_shipping.markup_per_lb", "3.75"
        )
        try:
            return float(param)
        except (TypeError, ValueError):
            return 3.75

    def _autohaus_cart_line_items(self):
        """Build FinditParts cart line items from the order lines.

        Maps each Odoo product to its linked ``finditparts.product`` record so
        the cart flow can quote the domestic US shipping rate. Lines without a
        linked FinditParts product are skipped.
        """
        self.ensure_one()
        products = self.order_line.mapped("product_id.product_tmpl_id")
        fp_products = self.env["finditparts.product"].sudo().search([
            ("odoo_product_id", "in", products.ids),
        ])
        fp_by_product = {fp.odoo_product_id.id: fp for fp in fp_products}

        items = []
        for line in self.order_line:
            if line.state == "cancel":
                continue
            if not line.product_id or line.is_delivery:
                continue
            if line.product_id.type in {"service", "combo"}:
                continue
            fp = fp_by_product.get(line.product_id.product_tmpl_id.id)
            if not fp or not fp.finditparts_id:
                continue
            try:
                quantity = int(line.product_uom_qty) or 1
            except (TypeError, ValueError):
                quantity = 1
            item = {
                "product_id": fp.finditparts_id,
                "quantity": quantity,
            }
            if fp.variant_id:
                item["variant_id"] = fp.variant_id
            items.append(item)
        return items

    @api.depends(
        "order_line.product_id",
        "order_line.product_uom_qty",
        "pickup_warehouse",
    )
    def _compute_logistics_usa_base_rate_hash(self):
        """Invalidate the cached US base rate when the cart content changes.

        The hash is derived from the FinditParts cart items (product + quantity)
        and the pickup warehouse. When it changes, the base rate is re-fetched
        from the API; otherwise the cached value is kept so the checkout does
        not create a new FinditParts cart on every price computation.
        """
        for order in self:
            items = order._autohaus_cart_line_items()
            digest = hashlib.md5(
                repr(
                    sorted(
                        (item["product_id"], item["quantity"])
                        for item in items
                    )
                ).encode("utf-8")
            ).hexdigest()
            if digest != order.logistics_usa_base_rate_hash:
                order.logistics_usa_base_rate_hash = digest
                if order._autohaus_destination_country() == "PA":
                    rate = order._fetch_usa_base_rate_from_api()
                    order.logistics_usa_base_rate = rate
                    if rate == 0.0:
                        _logger.warning(
                            "FinditParts US base rate fetch returned 0.0 for "
                            "order %s (items: %s)",
                            order.id,
                            items,
                        )
                else:
                    order.logistics_usa_base_rate = 0.0

    def _fetch_usa_base_rate_from_api(self):
        """Fetch the domestic US base rate from FinditParts (uncached).

        Creates a FinditParts cart, adds the order items and reads the
        ``/shipping_methods`` domestic US rates. Returns the ground rate (the
        base the Panama air quote is built on), or zero when the API does not
        answer so the quote degrades to the weight-only markup.
        """
        self.ensure_one()
        items = self._autohaus_cart_line_items()
        if not items:
            return 0.0
        config = self._autohaus_config()
        if not config:
            return 0.0
        try:
            from ..utils.api_client import FindinPartAPIClient

            client = FindinPartAPIClient(config)
            rates = client.get_shipping_rates("US", cart_items=items)
        except Exception:
            _logger.exception("FinditParts US base rate unavailable")
            return 0.0
        if not rates:
            return 0.0
        ground_rates = [
            rate
            for rate in rates
            if "ground" in (rate.get("label") or "").lower()
            or "ground" in (rate.get("service") or "").lower()
        ]
        chosen = ground_rates or rates
        return min(float(rate.get("base_rate") or 0.0) for rate in chosen)

    def _autohaus_usa_base_rate(self):
        """Return the cached US base rate, computing it on first access.

        Uses the stored value computed by ``_compute_logistics_usa_base_rate_hash``
        so repeated quote/pricing calls reuse a single FinditParts cart instead
        of creating one per call. A zero base rate for a Panama destination is
        treated as a stale cache (e.g. a previous failed fetch) and re-fetched.
        """
        self.ensure_one()
        if not self.logistics_usa_base_rate_hash:
            self._compute_logistics_usa_base_rate_hash()
        elif (
            self._autohaus_destination_country() == "PA"
            and self.logistics_usa_base_rate == 0.0
        ):
            self.logistics_usa_base_rate = self._fetch_usa_base_rate_from_api()
        return self.logistics_usa_base_rate or 0.0

    def _autohaus_cart_weight_lb(self):
        """Total real weight of the order in pounds (rounded up)."""
        self.ensure_one()
        carrier = self.env["delivery.carrier"]
        total = 0.0
        for line in self.order_line:
            if line.state == "cancel":
                continue
            if not line.product_id or line.is_delivery:
                continue
            if line.product_id.type in {"service", "combo"}:
                continue
            qty = line.product_uom_id._compute_quantity(
                line.product_uom_qty, line.product_id.uom_id
            )
            total += carrier._convert_weight(
                line.product_id.weight or 0.0,
                line.product_id.shipping_weight_unit,
                "lb",
            ) * qty
        return carrier._round_weight_for_delivery(total, "lb")

    def _autohaus_destination_country(self):
        """Return the ISO country code of the final delivery destination.

        The warehouse selection made at checkout is the primary signal: the
        USA hub means a domestic US delivery, Panama means the international
        destination. Falls back to the partner country when no warehouse was
        selected yet.
        """
        self.ensure_one()
        if self.pickup_warehouse == "panama":
            return "PA"
        if self.pickup_warehouse == "usa":
            return "US"
        partner = self.partner_shipping_id or self.partner_id
        if partner and partner.country_id:
            return partner.country_id.code or ""
        return "US"

    def _autohaus_enabled_panama_services(self):
        """Return the enabled Panama service codes (internal)."""
        config = self._autohaus_config()
        enabled = []
        if config:
            flags = {
                "ground": config.enable_shipping_ground,
                "rapido": config.enable_shipping_rapido,
                "flash": config.enable_shipping_flash,
                "lcl": config.enable_shipping_lcl,
            }
        else:
            Param = self.env["ir.config_parameter"].sudo()
            flags = {
                "ground": Param.get_param("autohaus_shipping.enable_panama_ground", "True") == "True",
                "rapido": Param.get_param("autohaus_shipping.enable_panama_rapido", "True") == "True",
                "flash": Param.get_param("autohaus_shipping.enable_panama_flash", "True") == "True",
                "lcl": Param.get_param("autohaus_shipping.enable_panama_lcl", "False") == "True",
            }
        return [code for code, is_enabled in flags.items() if is_enabled]

    def _autohaus_build_quote(self):
        """Build the PUBLIC shipping quote (safe for the customer).

        The US leg is free for the customer: the FinditParts domestic US rate is
        absorbed into the Panama air price as its base, and the commercial
        markup per pound is added on top. Only the final price, method label,
        transit window and delivery mode are exposed; the base rate and markup
        are never sent to the frontend.
        """
        self.ensure_one()
        dest_country = self._autohaus_destination_country()
        if dest_country != "PA":
            return {"destination": "usa", "rates": []}

        weight_lb = self._autohaus_cart_weight_lb()
        base_rate = self._autohaus_usa_base_rate()
        total = base_rate + self._autohaus_markup_per_lb() * weight_lb

        rates = []
        for service in self._autohaus_enabled_panama_services():
            definition = PANAMA_SERVICE_DEFS.get(service, {})
            eligible = service in PANAMA_AIR_SERVICES
            rates.append({
                "service": service,
                "label": definition.get("label", service),
                "transit": definition.get("transit", ""),
                "delivery": definition.get("delivery", ""),
                "eligible": eligible,
                "total": total if eligible else None,
            })
        return {"destination": "panama", "rates": rates}

    def _get_delivery_methods(self):
        """Filter delivery methods by destination and enabled services."""
        carriers = super()._get_delivery_methods()
        dest_country = self._autohaus_destination_country()
        if dest_country == "PA":
            enabled = set(self._autohaus_enabled_panama_services())
            return carriers.filtered(
                lambda c: c.panama_service_type in PANAMA_AIR_SERVICES
                and c.panama_service_type in enabled
            )
        return carriers.filtered(lambda c: not c.panama_service_type)
