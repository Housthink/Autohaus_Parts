from odoo import fields, models


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
