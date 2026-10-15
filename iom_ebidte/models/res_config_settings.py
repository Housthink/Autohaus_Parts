from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    iom_url = fields.Char(
        string='URL del middleware IOM',
        config_parameter='iom_url',
        help='URL base del middleware. En el servidor de Odoo, nunca localhost.',
    )
    iom_api_key = fields.Char(
        string='API key del cliente IOM',
        config_parameter='iom_api_key',
    )
    iom_sucursal = fields.Char(
        string='Codigo de sucursal',
        config_parameter='iom_sucursal',
        default='0001',
    )
    iom_punto_fiscal = fields.Char(
        string='Punto de facturacion fiscal',
        config_parameter='iom_punto_fiscal',
        default='001',
    )
    iom_tipo_documento = fields.Char(
        string='Tipo de documento',
        config_parameter='iom_tipo_documento',
        default='01',
        help='01 Factura, 02 Nota de debito, 03 Nota de credito.',
    )
    iom_tipo_contribuyente = fields.Selection(
        selection=[('1', 'Natural'), ('2', 'Juridico')],
        string='Tipo de contribuyente',
        config_parameter='iom_tipo_contribuyente',
        default='2',
    )
    iom_codigo_ubicacion = fields.Char(
        string='Codigo de ubicacion',
        config_parameter='iom_codigo_ubicacion',
        default='1-1-1',
        help='Formato provincia-distrito-corregimiento segun DGI.',
    )
    iom_tipo_cliente = fields.Selection(
        selection=[
            ('01', 'Contribuyente (01) - compra sujeto a ITBMS'),
            ('02', 'Consumidor final (02)'),
            ('03', 'Gobierno (03)'),
            ('04', 'Extranjero (04)'),
        ],
        string='Tipo de cliente FE',
        config_parameter='iom_tipo_cliente',
        help=(
            'Si se deja vacio, el modulo lo deduce: con RUC usa contribuyente '
            '(01) y sin RUC usa consumidor final (02).'
        ),
    )
    iom_unidad_medida_defecto = fields.Char(
        string='Unidad de medida por defecto',
        config_parameter='iom_unidad_medida_defecto',
        default='UND',
        help=(
            'Codigo de la Tabla 3 de EBI-PAC. Se usa cuando el producto no '
            'tiene "Unidad de medida EBI" cargada. El nombre de la unidad de '
            'Odoo no es un codigo valido para EBI.'
        ),
    )
    iom_corregimiento = fields.Char(
        string='Corregimiento',
        config_parameter='iom_corregimiento',
    )
    iom_timezone_offset = fields.Char(
        string='Offset horario',
        config_parameter='iom_timezone_offset',
        default='-05:00',
    )
    iom_timeout = fields.Char(
        string='Timeout HTTP (segundos)',
        config_parameter='iom_timeout',
        default='60',
    )
