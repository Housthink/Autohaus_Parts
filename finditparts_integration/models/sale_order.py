from datetime import timedelta

from odoo import api, fields, models


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
