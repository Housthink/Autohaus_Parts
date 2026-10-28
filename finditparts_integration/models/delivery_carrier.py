import math

from odoo import fields, models
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    weight_unit = fields.Selection(
        selection=[("lb", "lb"), ("kg", "kg")],
        string="Weight Unit",
        default="lb",
        required=True,
        help="Unit used by this delivery method for weight rules and pricing.",
    )

    @staticmethod
    def _convert_weight(weight, source_unit, target_unit):
        if source_unit == target_unit:
            return weight
        if source_unit == "lb" and target_unit == "kg":
            return weight * 0.453592
        if source_unit == "kg" and target_unit == "lb":
            return weight / 0.453592
        return weight

    @classmethod
    def _round_weight_for_delivery(cls, weight, unit):
        """Convert to the carrier unit and round positive weights upwards."""
        return math.ceil(weight) if weight > 0 else weight

    def _match_weight(self, source):
        self.ensure_one()
        if source._name == "sale.order":
            total_weight = sum(
                self._convert_weight(
                    line.product_id.weight or 0.0,
                    line.product_id.shipping_weight_unit,
                    self.weight_unit,
                ) * line.product_qty
                for line in source.order_line
            )
        elif source._name == "stock.picking":
            total_weight = sum(
                self._convert_weight(
                    move.product_id.weight or 0.0,
                    move.product_id.shipping_weight_unit,
                    self.weight_unit,
                ) * move.product_qty
                for move in source.move_ids
            )
        else:
            raise UserError("Invalid source document type")
        total_weight = self._round_weight_for_delivery(total_weight, self.weight_unit)
        return not self.max_weight or total_weight <= self.max_weight

    def _get_price_available(self, order):
        self.ensure_one()
        self = self.sudo()
        order = order.sudo()
        total = weight = volume = quantity = wv = 0
        for line in order.order_line:
            if line.state == "cancel":
                continue
            if not line.product_id or line.is_delivery:
                continue
            if line.product_id.type in {"service", "combo"}:
                continue
            qty = line.product_uom_id._compute_quantity(
                line.product_uom_qty, line.product_id.uom_id
            )
            weight += self._convert_weight(
                line.product_id.weight or 0.0,
                line.product_id.shipping_weight_unit,
                self.weight_unit,
            ) * qty
            volume += (line.product_id.volume or 0.0) * qty
            wv += self._convert_weight(
                line.product_id.weight or 0.0,
                line.product_id.shipping_weight_unit,
                self.weight_unit,
            ) * (line.product_id.volume or 0.0) * qty
            quantity += qty
        total = order._compute_amount_total_without_delivery()

        total = self._compute_currency(order, total, "pricelist_to_company")
        context_weight = self.env.context.get("order_weight")
        weight = context_weight if context_weight is not None else weight
        weight = self._round_weight_for_delivery(weight, self.weight_unit)
        return self._get_price_from_picking(total, weight, volume, quantity, wv=wv)
