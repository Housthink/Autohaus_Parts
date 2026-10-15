from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.iom_ebidte.models import iom_client
from odoo.addons.iom_ebidte.models.iom_client import IOMClient, IOMError
from odoo.exceptions import UserError
from odoo.tests import tagged


class ClienteFalso:
    """Reemplaza al cliente HTTP para probar la logica sin tocar la red.

    `fallan_las_primeras` hace que las primeras N emisiones disparen IOMError,
    para simular a EBI rechazando y verificar que el lote no se cae.
    """

    def __init__(self, emitidas, fallan_las_primeras=0):
        self.emitidas = emitidas
        self.fallan_las_primeras = fallan_las_primeras
        self.intentos = 0

    def emit(self, payload):
        self.intentos += 1
        if self.intentos <= self.fallan_las_primeras:
            raise IOMError('EBI rechazo simulado')
        numero = payload['documento']['datosTransaccion']['numeroDocumentoFiscal']
        self.emitidas.append(numero)
        return {
            'cufe': 'CUFE-SIM-' + numero,
            'datosEnvio': {'protocolo': 'PR-' + numero},
        }


@tagged('post_install', '-at_install')
class TestIOMDisparadoras(AccountTestInvoicingCommon):
    """Cubre las tres vias de disparo: boton, accion de servidor y cron."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pa_country = cls.env.ref('base.pa')
        cls.pa_state = cls.env['res.country.state'].create({
            'name': 'Panama',
            'code': '01',
            'country_id': cls.pa_country.id,
        })
        cls.tax = cls.env['account.tax'].create({
            'name': 'ITBMS 7% disparadoras',
            'amount_type': 'percent',
            'amount': 7.0,
            'type_tax_use': 'sale',
            'company_id': cls.env.company.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Producto disparadoras',
            'list_price': 100.0,
            'taxes_id': [(6, 0, cls.tax.ids)],
            'iom_unidad_medida': 'UND',
        })
        cls._secuencia = 0

    def _factura(self, con_ruc=True):
        self._secuencia += 1
        partner = self.env['res.partner'].create({
            'name': 'Cliente %d' % self._secuencia,
            'vat': '123456789010%03d' % self._secuencia if con_ruc else False,
            'street': 'Calle 50',
            'country_id': self.pa_country.id,
            'state_id': self.pa_state.id,
            'city': 'Panama',
        })
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'company_id': self.env.company.id,
            'invoice_date': '2026-10-01',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        move.action_post()
        return move

    def _forzar_contribuyente(self):
        """Fija el tipo de cliente en contribuyente.

        Sin esto, una factura sin RUC se deduce como consumidor final (02) y es
        valida. Para provocar el error hace falta exigir RUC.
        """
        self.env['ir.config_parameter'].sudo().set_param('iom_tipo_cliente', '01')

    def _con_cliente(self, cliente):
        """Parchea IOMClient para que las pruebas no hablen con el middleware.

        No se llama al ``__init__`` real a proposito: este exigiria `iom_url` y
        `iom_api_key` configurados, que es justo lo que las pruebas no quieren
        depender.
        """
        def init(self, env):
            self.env = env
            self.base_url = 'http://test.invalid'
            self.api_key = 'test'
            self.timeout = 1
            self.emit = cliente.emit

        return patch.object(iom_client.IOMClient, '__init__', init)

    # ------------------------------------------------------------------
    # Via 1: emision individual
    # ------------------------------------------------------------------

    def test_individual_acepta_y_guarda_cufe(self):
        move = self._factura()
        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            move.action_iom_emitir()

        self.assertEqual(move.iom_estado_dte, 'aceptado')
        self.assertEqual(move.iom_cufe, 'CUFE-SIM-' + cliente.emitidas[0])
        self.assertEqual(move.iom_protocolo, 'PR-' + cliente.emitidas[0])

    def test_individual_aborta_en_el_primer_error(self):
        """La via individual es todo o nada: una mala frena a las demas."""
        self._forzar_contribuyente()
        buena1 = self._factura()
        mala = self._factura(con_ruc=False)
        buena2 = self._factura()

        cliente = ClienteFalso([])
        # Ojo: no se usa assertRaises a proposito. El de Odoo abre un
        # savepoint y lo revierte cuando salta la excepcion esperada
        # (tests/common.py::_assertRaises), asi que las escrituras de la
        # factura que si se emitio se perderian y no habria forma de
        # comprobar que el lote quedo a medias.
        with self._con_cliente(cliente):
            try:
                (buena1 + mala + buena2).action_iom_emitir()
            except UserError as error:
                self.assertIn('necesita RUC', str(error))
            else:
                self.fail('Se esperaba un UserError por la factura sin RUC')

        # La tercera nunca se intento.
        self.assertEqual(len(cliente.emitidas), 1)
        self.assertEqual(buena1.iom_estado_dte, 'aceptado')
        self.assertEqual(mala.iom_estado_dte, 'borrador')
        self.assertEqual(buena2.iom_estado_dte, 'borrador')

    def test_individual_rechaza_reenvio(self):
        move = self._factura()
        move.iom_estado_dte = 'aceptado'
        with self._con_cliente(ClienteFalso([])):
            with self.assertRaises(UserError):
                move.action_iom_emitir()

    # ------------------------------------------------------------------
    # Via 2: emision en lote
    # ------------------------------------------------------------------

    def test_lote_aisla_el_error_y_no_frena_al_resto(self):
        self._forzar_contribuyente()
        buena1 = self._factura()
        mala = self._factura(con_ruc=False)
        buena2 = self._factura()

        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            action = (buena1 + mala + buena2).action_iom_emitir_lote()

        self.assertEqual(buena1.iom_estado_dte, 'aceptado')
        self.assertEqual(buena2.iom_estado_dte, 'aceptado')
        self.assertEqual(mala.iom_estado_dte, 'borrador')
        self.assertEqual(len(cliente.emitidas), 2)
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Con error: 1', action['params']['message'])

    def test_lote_sobrevive_a_error_de_eBI(self):
        """Un rechazo de EBI tampoco debe voltear el lote."""
        facturas = self.env['account.move'].browse([
            self._factura().id,
            self._factura().id,
            self._factura().id,
        ])

        cliente = ClienteFalso([], fallan_las_primeras=2)
        with self._con_cliente(cliente):
            action = facturas.action_iom_emitir_lote()

        estados = facturas.mapped('iom_estado_dte')
        self.assertEqual(estados.count('aceptado'), 1)
        self.assertEqual(estados.count('rechazado'), 2)
        self.assertEqual(action['params']['type'], 'warning')

    def test_lote_distingue_omitidas_de_errores(self):
        buena = self._factura()
        buena.iom_estado_dte = 'aceptado'  # ya enviada: se omite, no es error

        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            action = buena.action_iom_emitir_lote()

        self.assertEqual(len(cliente.emitidas), 0)
        self.assertIn('Omitidas: 1', action['params']['message'])
        # Sin nada emitido y sin errores, el aviso es informativo.
        self.assertEqual(action['params']['type'], 'info')

    def test_lote_todo_ok_avisa_exito(self):
        facturas = self.env['account.move'].browse([
            self._factura().id,
            self._factura().id,
        ])
        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            action = facturas.action_iom_emitir_lote()

        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(facturas.mapped('iom_estado_dte'), ['aceptado', 'aceptado'])

    def test_omitida_si_no_esta_confirmada(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self._factura().partner_id.id,
            'company_id': self.env.company.id,
            'invoice_date': '2026-10-01',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            resultado, mensaje = move._iom_emitir_una(cliente)

        self.assertEqual(resultado, 'omitida')
        self.assertIn('borrador', mensaje)
        self.assertEqual(len(cliente.emitidas), 0)

    # ------------------------------------------------------------------
    # Via 3: cron
    # ------------------------------------------------------------------

    def test_cron_solo_toma_pendientes_confirmadas(self):
        pendiente = self._factura()
        ya_emitida = self._factura()
        ya_emitida.action_iom_emitir  # no se llama: se marca a mano
        ya_emitida.iom_estado_dte = 'aceptado'
        en_borrador = self._factura()
        en_borrador.button_draft()

        cliente = ClienteFalso([])
        with self._con_cliente(cliente):
            facturas = self.env['account.move'].search([
                ('iom_estado_dte', '=', 'borrador'),
                ('state', '=', 'posted'),
                ('move_type', '=', 'out_invoice'),
                ('id', 'in', (pendiente + ya_emitida + en_borrador).ids),
            ])
            facturas.action_iom_emitir_lote()

        self.assertEqual(pendiente.iom_estado_dte, 'aceptado')
        self.assertEqual(ya_emitida.iom_estado_dte, 'aceptado')
        self.assertEqual(en_borrador.iom_estado_dte, 'borrador')
        self.assertEqual(len(cliente.emitidas), 1)

    def test_cron_definido_pero_inactivo(self):
        """Se entrega apagado: que la activacion sea una decision consciente."""
        cron = self.env.ref('iom_ebidte.ir_cron_iom_emitir_pendientes')
        self.assertFalse(cron.active)
        self.assertEqual(cron.state, 'code')
        self.assertEqual(cron.interval_type, 'minutes')

    def test_acciones_de_servidor_registradas(self):
        individual = self.env.ref('iom_ebidte.action_iom_emitir_servidor')
        lote = self.env.ref('iom_ebidte.action_iom_emitir_lote')

        self.assertEqual(individual.state, 'code')
        self.assertEqual(lote.state, 'code')
        self.assertIn('action_iom_emitir()', individual.code)
        self.assertIn('action_iom_emitir_lote()', lote.code)