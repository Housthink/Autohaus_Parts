from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    iom_unidad_medida = fields.Char(
        string='Unidad de medida EBI',
        size=20,
        help=(
            'Codigo de unidad de medida segun la Tabla 3 de EBI-PAC. '
            'Si se deja vacio se usa el parametro "Unidad de medida por '
            'defecto" de la configuracion IOM. Ojo: el nombre de la unidad '
            'de Odoo no es un codigo valido para EBI.'
        ),
    )
