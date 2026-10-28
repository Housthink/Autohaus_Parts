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

        The FinditParts API does not return a base rate yet, so the Panama air
        price is the markup per pound times the billable weight in pounds
        (rounded up). Only the final price, method label, transit window and
        delivery mode are exposed; the markup rate is never sent to the
        frontend.
        """
        self.ensure_one()
        dest_country = self._autohaus_destination_country()
        if dest_country != "PA":
            return {"destination": "usa", "rates": []}

        weight_lb = self._autohaus_cart_weight_lb()
        total = self._autohaus_markup_per_lb() * weight_lb

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
