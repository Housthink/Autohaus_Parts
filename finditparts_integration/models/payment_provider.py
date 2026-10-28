from odoo import models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _stripe_get_country(self, country_code):
        # Stripe does not support Panama (PA) for Express Checkout (Apple Pay /
        # Google Pay / Payment Request). Fall back to the US country code so the
        # payment request can be created without raising an IntegrationError.
        if country_code == 'PA':
            country_code = 'US'
        return super()._stripe_get_country(country_code)
