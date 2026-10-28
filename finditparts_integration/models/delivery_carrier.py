import math

from odoo import api, fields, models
from odoo.exceptions import UserError

# Internal service definitions for Panama shipping. These are used by the
# quoting engine and the checkout UI. Only the "label", "transit" and
# "delivery" values are safe to expose publicly; base rates and markup rules
# must never be sent to the frontend.
PANAMA_SERVICE_DEFS = {
    "ground": {
        "label": "Ground · aéreo",
        "transit": "6–7 días hábiles",
        "delivery": "Retiro en nuestro local",
    },
    "rapido": {
        "label": "Rápido · aéreo",
        "transit": "4–5 días hábiles",
        "delivery": "Retiro en nuestro local",
    },
    "flash": {
        "label": "Flash · aéreo",
        "transit": "2–3 días hábiles",
        "delivery": "Según confirmación del pedido",
    },
    "lcl": {
        "label": "Marítimo · LCL",
        "transit": "10–15 días hábiles",
        "delivery": "Según confirmación del pedido",
    },
}

# Air services that use the per-pound markup. LCL uses volume, which cannot be
# computed from the API (no dimensions), so it is quoted manually.
PANAMA_AIR_SERVICES = ("ground", "rapido", "flash")


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    weight_unit = fields.Selection(
        selection=[("lb", "lb"), ("kg", "kg")],
        string="Weight Unit",
        default="lb",
        required=True,
        help="Unit used by this delivery method for weight rules and pricing.",
    )

    panama_service_type = fields.Selection(
        selection=[
            ("ground", "Ground · aéreo"),
            ("rapido", "Rápido · aéreo"),
            ("flash", "Flash · aéreo"),
            ("lcl", "Marítimo · LCL"),
        ],
        string="Panama Service Type",
        help="Panama shipping service this carrier represents. Used by the "
             "Autohaus quoting engine to apply the corresponding commercial "
             "markup on top of the FinditParts base rate.",
    )

    panama_transit_label = fields.Char(
        string="Transit Window",
        compute="_compute_panama_service_labels",
        help="Public transit window shown to the customer (days hábiles).",
    )
    panama_delivery_label = fields.Char(
        string="Delivery Mode",
        compute="_compute_panama_service_labels",
        help="Public delivery/retiro mode shown to the customer.",
    )

    @api.depends("panama_service_type")
    def _compute_panama_service_labels(self):
        for carrier in self:
            definition = PANAMA_SERVICE_DEFS.get(carrier.panama_service_type or "", {})
            carrier.panama_transit_label = definition.get("transit", "")
            carrier.panama_delivery_label = definition.get("delivery", "")

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

    def _is_available_for_order(self, order):
        """Panama air services are available when a price rule can be matched.

        LCL is never auto-quoted because the API provides no dimensions, so
        there is no billable volume. The destination check is handled by
        ``sale.order._get_delivery_methods``, so the native country matching is
        bypassed for Panama carriers (the checkout warehouse selection, not the
        partner country, determines the final destination).
        """
        if self.panama_service_type in PANAMA_AIR_SERVICES:
            return True
        if self.panama_service_type == "lcl":
            return False
        return super()._is_available_for_order(order)
