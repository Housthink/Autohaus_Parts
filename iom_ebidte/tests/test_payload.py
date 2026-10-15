from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.iom_ebidte.models.iom_client import IOMClient
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestIOMPayload(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pa_country = cls.env.ref('base.pa')
        # Esta base no trae el catalogo de provincias de Panama cargado, asi
        # que se crea una solo para el fixture.
        cls.pa_state = cls.env['res.country.state'].create({
            'name': 'Panama',
            'code': '01',
            'country_id': cls.pa_country.id,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente de Prueba SA',
            'vat': '12345678901234',
            'street': 'Calle 50',
            'country_id': cls.pa_country.id,
            'state_id': cls.pa_state.id,
            'city': 'Panama',
            'company_id': cls.env.company.id,
        })
        cls.tax = cls.env['account.tax'].create({
            'name': 'IOM ITBMS 7%',
            'amount_type': 'percent',
            'amount': 7.0,
            'type_tax_use': 'sale',
            'company_id': cls.env.company.id,
        })
        product = cls.env['product.product'].create({
            'name': 'Producto de prueba',
            'list_price': 546.0,
            'taxes_id': [(6, 0, cls.tax.ids)],
        })
        cls.move = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'company_id': cls.env.company.id,
            'invoice_date': '2026-10-01',
            'date': '2026-10-01',
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1.0,
                'price_unit': 546.0,
            })],
        })

    def _payload(self):
        self.move.action_post()
        return self.move._iom_build_payload()

    def test_numero_documento_va_padded(self):
        payload = self._payload()
        numero = payload['documento']['datosTransaccion']['numeroDocumentoFiscal']
        self.assertEqual(len(numero), 10)
        self.assertTrue(numero.isdigit())

    def test_tasa_itbms_por_porcentaje(self):
        payload = self._payload()
        item = payload['documento']['listaItems'][0]
        self.assertEqual(item['tasaITBMS'], '01')

    def test_totales_cuadran(self):
        totales = self._payload()['documento']['totalesSubTotales']
        neto = float(totales['totalPrecioNeto'])
        impuesto = float(totales['totalITBMS'])
        total = float(totales['totalFactura'])
        self.assertAlmostEqual(neto + impuesto, total, places=2)

    def test_nro_items_coincide(self):
        payload = self._payload()
        totales = payload['documento']['totalesSubTotales']
        items = payload['documento']['listaItems']
        self.assertEqual(int(totales['nroItems']), len(items))

    def test_exige_ruc(self):
        self.move.action_post()
        # El tipo se fija en contribuyente: en ese caso el RUC es obligatorio.
        self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '01')
        try:
            self.partner.vat = False
            with self.assertRaises(UserError):
                self.move._iom_build_payload()
        finally:
            self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '')

    def test_fecha_tiene_offset_panama(self):
        payload = self._payload()
        fecha = payload['documento']['datosTransaccion']['fechaEmision']
        self.assertTrue(fecha.endswith('-05:00'), fecha)

    def test_rechaza_reenvio(self):
        self.move.action_post()
        self.move.iom_estado_dte = 'aceptado'
        with self.assertRaises(Exception):
            self.move.action_iom_emitir()

    def test_digito_verificador_padded_a_dos(self):
        cliente = self._payload()['documento']['datosTransaccion']['cliente']
        self.assertEqual(cliente['digitoVerificadorRUC'], '04')

    def test_ruc_tipo_cliente_contribuyente(self):
        cliente = self._payload()['documento']['datosTransaccion']['cliente']
        self.assertEqual(cliente['tipoClienteFE'], '01')

    def test_ubicacion_obligatoria_para_contribuyente(self):
        self.move.action_post()
        self.partner.state_id = False
        self.partner.city = False
        with self.assertRaises(UserError):
            self.move._iom_build_payload()

    def test_ruc_obligatorio_para_contribuyente(self):
        self.move.action_post()
        self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '01')
        try:
            self.partner.vat = False
            with self.assertRaises(UserError):
                self.move._iom_build_payload()
        finally:
            self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '')

    def test_sin_ruc_es_consumidor_final(self):
        self.move.action_post()
        self.partner.vat = False
        cliente = self.move._iom_build_cliente(self.partner)
        self.assertEqual(cliente['tipoClienteFE'], '02')
        self.assertNotIn('numeroRUC', cliente)
        self.assertNotIn('digitoVerificadorRUC', cliente)
        self.assertNotIn('razonSocial', cliente)

    def test_consumidor_final_no_exige_ubicacion(self):
        self.move.action_post()
        self.partner.vat = False
        self.partner.state_id = False
        self.partner.city = False
        cliente = self.move._iom_build_cliente(self.partner)
        self.assertEqual(cliente['tipoClienteFE'], '02')

    def test_extranjero_no_soportado(self):
        self.move.action_post()
        self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '04')
        try:
            with self.assertRaises(UserError):
                self.move._iom_build_payload()
        finally:
            self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '')

    def test_unidad_medida_usa_codigo_no_nombre(self):
        item = self._payload()['documento']['listaItems'][0]
        self.assertNotIn(' ', item['unidadMedida'])
        self.assertTrue(item['unidadMedida'])

    def test_cliente_acepta_exito_por_status(self):
        self.assertTrue(IOMClient._es_exitoso({'status': 'ok', 'id': 'MOCK-1'}))
        self.assertTrue(IOMClient._es_exitoso({'codigo': '200'}))
        self.assertTrue(IOMClient._es_exitoso({'cufe': 'ABC'}))
        self.assertFalse(IOMClient._es_exitoso({'status': 'error'}))
        self.assertFalse(IOMClient._es_exitoso({'codigo': '100'}))
