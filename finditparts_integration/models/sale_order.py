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
