from odoo import fields, models


class CustomerRequest(models.Model):
    _name = "finditparts.customer.request"
    _description = "Customer Return and Warranty Request"
    _order = "create_date desc"

    name = fields.Char(string="Request", required=True, default="New", copy=False)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    sale_order_id = fields.Many2one("sale.order", string="Order", ondelete="set null")
    request_type = fields.Selection(
        [("return", "Devolución"), ("warranty", "Garantía")],
        required=True,
        default="return",
    )
    state = fields.Selection(
        [("draft", "Recibida"), ("review", "En revisión"), ("approved", "Aprobada"),
         ("rejected", "Rechazada"), ("done", "Completada")],
        default="draft",
        required=True,
    )
    reason = fields.Char(required=True)
    description = fields.Text()
    create_date = fields.Datetime(readonly=True)

