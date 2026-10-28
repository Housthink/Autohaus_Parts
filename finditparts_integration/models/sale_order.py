import json
from datetime import timedelta

from odoo import api, fields, models

from .delivery_carrier import PANAMA_AIR_SERVICES, PANAMA_SERVICE_DEFS


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

    shipping_quote_json = fields.Text(
        string="Shipping Quote Snapshot (internal)",
        copy=False,
        groups="base.group_system",
        help="Internal snapshot of the last shipping quote: base rates, markup "
             "and billable weight. Restricted to system users; never exposed "
             "on the website or to the customer.",
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
            "autohaus_shipping.markup_per_lb", "2.50"
        )
        try:
            return float(param)
        except (TypeError, ValueError):
            return 2.50

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

    def _autohaus_quote_snapshot(self):
        """Parse the stored quote snapshot (internal)."""
        self.ensure_one()
        raw = self.sudo().shipping_quote_json
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}

    def _autohaus_get_base_rate(self, service_type):
        """Return the stored base rate for a Panama service, or None."""
        snapshot = self._autohaus_quote_snapshot()
        for rate in snapshot.get("rates", []):
            if rate.get("service") == service_type and rate.get("eligible"):
                return rate.get("base_rate")
        return None

    def _autohaus_quote_panama_air(self, service_type, base_rate):
        """Compute the public price of a Panama air service (internal).

        Only the total price is safe to expose. This method returns the full
        internal breakdown; the public payload is built separately.
        """
        if base_rate is None:
            return None
        weight_lb = self._autohaus_cart_weight_lb()
        markup_per_lb = self._autohaus_markup_per_lb()
        markup_total = markup_per_lb * weight_lb
        return {
            "service": service_type,
            "base_rate": base_rate,
            "markup_per_lb": markup_per_lb,
            "markup_total": markup_total,
            "billable_weight_lb": weight_lb,
            "total": base_rate + markup_total,
            "eligible": True,
        }

    def _autohaus_build_public_quote(self, internal_rates):
        """Build the customer-facing quote (never exposes base rate/markup)."""
        public = []
        for rate in internal_rates:
            service_type = rate.get("service")
            definition = PANAMA_SERVICE_DEFS.get(service_type, {})
            public.append({
                "service": service_type,
                "label": definition.get("label", service_type),
                "transit": definition.get("transit", ""),
                "delivery": definition.get("delivery", ""),
                "eligible": bool(rate.get("eligible")),
                # Only include the final price for eligible methods.
                "total": rate.get("total") if rate.get("eligible") else None,
            })
        return public

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

    def _autohaus_cart_items(self):
        """Build a lightweight cart payload for the shipping API."""
        items = []
        for line in self.order_line:
            if line.state == "cancel":
                continue
            if not line.product_id or line.is_delivery:
                continue
            if line.product_id.type in {"service", "combo"}:
                continue
            items.append({
                "sku": line.product_id.default_code or "",
                "quantity": line.product_uom_qty,
            })
        return items

    def _autohaus_fetch_base_rates(self, dest_country, dest_zip=None):
        """Fetch FinditParts base rates, keyed by internal service code."""
        config = self._autohaus_config()
        if not config:
            return {}
        try:
            from ..utils.api_client import FindinPartAPIClient
            client = FindinPartAPIClient(config)
            raw_rates = client.get_shipping_rates(
                dest_country,
                dest_zip=dest_zip,
                cart_items=self._autohaus_cart_items(),
            )
        except Exception:
            raw_rates = []

        base_rates = {}
        for rate in raw_rates:
            service = self._autohaus_map_api_service(rate.get("service", ""))
            if service and rate.get("eligible"):
                base_rates.setdefault(service, rate.get("base_rate"))
        return base_rates

    @staticmethod
    def _autohaus_map_api_service(service_code):
        """Normalize an unknown API service code to an internal Panama code."""
        code = (service_code or "").strip().lower()
        if code in ("ground", "standard", "economy", "home_delivery"):
            return "ground"
        if code in ("rapido", "expedited", "second_day", "2day"):
            return "rapido"
        if code in ("flash", "express", "next_day", "overnight", "priority"):
            return "flash"
        if code in ("lcl", "ocean", "maritimo", "sea"):
            return "lcl"
        return None

    def _autohaus_build_quote(self):
        """Compute the shipping quote for the order and return the PUBLIC
        payload (safe for the customer). Stores the internal snapshot on the
        order. Never exposes base rates, markup or formulas.
        """
        self.ensure_one()
        dest_country = self._autohaus_destination_country()

        self._autohaus_refresh_base_rates()
        snapshot = self._autohaus_quote_snapshot()
        public = self._autohaus_build_public_quote(snapshot.get("rates", []))
        return {"destination": "panama" if dest_country == "PA" else "usa", "rates": public}

    def _autohaus_quote_is_fresh(self):
        """Whether the stored quote is recent enough to reuse (internal)."""
        snapshot = self._autohaus_quote_snapshot()
        date_str = snapshot.get("date")
        if not date_str:
            return False
        if snapshot.get("weight_lb") != self._autohaus_cart_weight_lb():
            return False
        try:
            quoted = fields.Datetime.from_string(date_str)
        except (ValueError, TypeError):
            return False
        return (fields.Datetime.now() - quoted).total_seconds() < self._autohaus_quote_ttl()

    @staticmethod
    def _autohaus_quote_ttl():
        """TTL in seconds for the internal quote snapshot cache."""
        return 60

    def _autohaus_refresh_base_rates(self):
        """Fetch FinditParts base rates and rebuild the internal snapshot.

        Idempotent and cached: it does nothing when the stored quote is fresh.
        Never raises; when the API is unavailable the affected methods are
        stored as ineligible (cotización pendiente) instead of US$0.
        """
        self.ensure_one()
        if self._autohaus_quote_is_fresh():
            return

        dest_country = self._autohaus_destination_country()
        dest_zip = (self.partner_shipping_id or self.partner_id).zip or None
        base_rates = self._autohaus_fetch_base_rates(dest_country, dest_zip=dest_zip)

        if dest_country == "PA":
            enabled = self._autohaus_enabled_panama_services()
            internal_rates = []
            for service in enabled:
                if service in PANAMA_AIR_SERVICES:
                    rate = self._autohaus_quote_panama_air(service, base_rates.get(service))
                    if rate is None:
                        rate = {"service": service, "eligible": False, "total": None}
                    internal_rates.append(rate)
                elif service == "lcl":
                    internal_rates.append({"service": "lcl", "eligible": False, "total": None})
        else:
            internal_rates = []
            for service_code, base_rate in base_rates.items():
                internal_rates.append({
                    "service": service_code,
                    "base_rate": base_rate,
                    "markup_per_lb": 0.0,
                    "markup_total": 0.0,
                    "billable_weight_lb": self._autohaus_cart_weight_lb(),
                    "total": base_rate,
                    "eligible": True,
                })

        self.sudo()._autohaus_store_snapshot(
            dest_country=dest_country, internal_rates=internal_rates
        )

    def _get_delivery_methods(self):
        """Filter delivery methods by destination and quotability."""
        carriers = super()._get_delivery_methods()
        dest_country = self._autohaus_destination_country()
        if dest_country == "PA":
            return carriers.filtered(lambda c: c.panama_service_type in PANAMA_AIR_SERVICES)
        return carriers.filtered(lambda c: not c.panama_service_type)

    def _autohaus_store_snapshot(self, dest_country, internal_rates):
        """Persist the internal quote snapshot (system-only access)."""
        snapshot = {
            "date": fields.Datetime.to_string(fields.Datetime.now()),
            "destination": dest_country,
            "weight_lb": self._autohaus_cart_weight_lb(),
            "markup_per_lb": self._autohaus_markup_per_lb(),
            "currency": "USD",
            "rates": internal_rates,
        }
        self.sudo().shipping_quote_json = json.dumps(snapshot)
