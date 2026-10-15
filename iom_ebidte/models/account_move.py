import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .iom_client import IOMClient, IOMError

_logger = logging.getLogger(__name__)

# Catalogo ITBMS de EBI: 00 exento, 01 7%, 02 10%, 03 15%.
_ITBMS_POR_PORCENTAJE = (
    (7.5, '01'),
    (12.5, '02'),
)


def _tasa_itbms(base, impuesto):
    """Deriva el codigo ITBMS del importe en vez de leer el grupo de impuesto.

    Odoo 19 no expone `tax_group_type` en account.tax.group, y calcular el
    porcentaje desde los importes evita depender de ese campo.
    """
    porcentaje = round((impuesto / base * 100), 2) if base else 0.0
    if porcentaje == 0:
        return '00'
    for limite, codigo in _ITBMS_POR_PORCENTAJE:
        if porcentaje <= limite:
            return codigo
    return '03'


class AccountMove(models.Model):
    _inherit = 'account.move'

    iom_estado_dte = fields.Selection(
        selection=[
            ('borrador', 'No enviado'),
            ('enviando', 'Enviando'),
            ('aceptado', 'Aceptado por DGI'),
            ('rechazado', 'Rechazado'),
            ('anulado', 'Anulado'),
        ],
        string='Estado DTE',
        default='borrador',
        copy=False,
        readonly=True,
        tracking=True,
    )
    iom_cufe = fields.Char(string='CUFE', copy=False, readonly=True)
    iom_qr = fields.Char(string='QR', copy=False, readonly=True)
    iom_protocolo = fields.Char(string='Protocolo', copy=False, readonly=True)
    iom_respuesta = fields.Text(string='Respuesta EBI', copy=False, readonly=True)
    iom_fecha_envio = fields.Datetime(
        string='Fecha de envio', copy=False, readonly=True
    )
    iom_fecha_aceptacion = fields.Datetime(
        string='Fecha de aceptacion DGI', copy=False, readonly=True
    )

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------
    def _iom_param(self, key, default=None):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _iom_unidad_medida(self, line):
        """Codigo de unidad de medida segun la Tabla 3 de EBI.

        Odoo guarda el nombre de la unidad ("Units", "m"), pero EBI exige un
        codigo corto del catalogo oficial. El codigo sale del parametro
        `iom_unidad_medida_defecto`; se permite sobreescribirlo por linea con
        el campo `iom_unidad_medida` del producto, si esta cargado.
        """
        codigo = ''
        producto = line.product_id
        if producto:
            codigo = (producto.iom_unidad_medida or '').strip()
        if not codigo:
            codigo = (self._iom_param('iom_unidad_medida_defecto') or 'UND').strip()
        return codigo[:20]

    def _iom_build_item(self, line):
        base = line.price_subtotal
        impuesto = line.price_total - line.price_subtotal
        cantidad = line.quantity or 1.0

        return {
            'descripcion': (line.name or 'Item')[:500],
            'cantidad': '%.2f' % cantidad,
            'unidadMedida': self._iom_unidad_medida(line),
            'precioUnitario': '%.2f' % (base / cantidad if cantidad else base),
            'precioUnitarioDescuento': '0.00',
            'precioItem': '%.2f' % base,
            'valorTotal': '%.2f' % line.price_total,
            'codigoGTIN': '0',
            'cantGTINCom': '%.2f' % cantidad,
            'codigoGTINInv': '0',
            'cantGTINComInv': '%.2f' % cantidad,
            'tasaITBMS': _tasa_itbms(base, impuesto),
            'valorITBMS': '%.2f' % impuesto,
        }

    def _iom_tipo_cliente(self, ruc):
        """Deduce el tipo de receptor segun EBI.

        01 contribuyente, 02 consumidor final, 03 gobierno, 04 extranjero.
        Si el parametro esta definido manda el parametro; si no, se deduce:
        con RUC es contribuyente, sin RUC es consumidor final.
        """
        configurado = str(self._iom_param('iom_tipo_cliente') or '').strip()
        if configurado:
            return configurado
        return '01' if ruc else '02'

    def _iom_build_cliente(self, partner):
        """Arma el bloque `cliente` de la FE segun las reglas de EBI.

        Reglas que se respetan aca (docs /api/Enviar):

        * 01/03 (contribuyente/gobierno): obligan RUC, digito verificador,
          razon social y provincia/distrito/corregimiento.
        * 02 (consumidor final): el RUC es opcional (puede ir la cedula), y no
          se manda digito verificador ni razon social.
        * 04 (extranjero): no se manda RUC ni DV; exige identificacion del
          extranjero, que este modulo todavia no soporta.
        """
        ruc = (partner.vat or '').strip()
        tipo_cliente = self._iom_tipo_cliente(ruc)
        es_contribuyente = tipo_cliente in ('01', '03')

        provincia = (partner.state_id.name or '').strip()
        distrito = (partner.city or '').strip()
        # res.partner no tiene un campo estandar de corregimiento: se usa el
        # parametro del sistema y, si no esta, se repite el distrito.
        corregimiento = (self._iom_param('iom_corregimiento') or '').strip() or distrito
        codigo_ubicacion = str(
            self._iom_param('iom_codigo_ubicacion') or '1-1-1'
        ).strip()

        if es_contribuyente:
            faltantes = [
                nombre
                for nombre, valor in (
                    ('RUC', ruc),
                    ('provincia', provincia),
                    ('distrito', distrito),
                    ('corregimiento', corregimiento),
                )
                if not valor
            ]
            if faltantes:
                raise UserError(
                    _(
                        'El contacto %s se emite como contribuyente (%s) y necesita %s. '
                        'Cargalo en la ficha del contacto o en la configuracion IOM.'
                    ) % (partner.display_name, tipo_cliente, ', '.join(faltantes))
                )

        if tipo_cliente == '04':
            raise UserError(
                _(
                    'El contacto %s esta marcado como extranjero (tipoClienteFE 04). '
                    'Ese caso requiere tipo de identificacion y numero de '
                    'identificacion del extranjero, que todavia no esta soportado.'
                ) % partner.display_name
            )

        cliente = {
            'tipoClienteFE': tipo_cliente,
            'pais': partner.country_id.code or self._iom_param('iom_pais', 'PA'),
            'direccion': (partner.street or '').strip()[:100],
            'codigoUbicacion': codigo_ubicacion,
            'provincia': provincia[:100],
            'distrito': distrito[:100],
            'corregimiento': corregimiento[:100],
            'correoElectronico1': partner.email or '',
        }

        # EBI: numeroRUC y digitoVerificadorRUC no van si tipoClienteFE = 04.
        # Para 02 el RUC es opcional; el DV solo es obligatorio en 01/03 y su
        # formato es N|2, asi que se completa con cero a la izquierda.
        if ruc:
            cliente['numeroRUC'] = ruc[:20]
            if es_contribuyente:
                digito = ruc[-1] if ruc[-1].isdigit() else '0'
                cliente['digitoVerificadorRUC'] = digito.zfill(2)

        if es_contribuyente:
            cliente.update({
                'tipoContribuyente': str(
                    self._iom_param('iom_tipo_contribuyente') or '2'
                ).strip(),
                'razonSocial': (partner.name or '').strip()[:200],
            })

        return cliente

    def _iom_build_payload(self):
        self.ensure_one()

        if not self.sequence_number:
            raise UserError(
                _('La factura %s no tiene numero de secuencia.', self.name)
            )

        lineas = self.invoice_line_ids.filtered(
            lambda line: line.display_type == 'product'
        )
        if not lineas:
            raise UserError(
                _('La factura %s no tiene lineas de producto.', self.name)
            )

        items = [self._iom_build_item(line) for line in lineas]

        suma_neto = sum(line.price_subtotal for line in lineas)
        suma_impuesto = sum(
            line.price_total - line.price_subtotal for line in lineas
        )
        suma_total = sum(line.price_total for line in lineas)

        # Factura a credito si queda saldo pendiente; efectivo si esta pagada.
        pendiente = self.amount_residual
        if pendiente and pendiente > 0.01:
            forma_pago = '01'
            tiempo_pago = '2'
        else:
            forma_pago = '02'
            tiempo_pago = '1'

        # EBI espera la hora de Panama (UTC-5) explicita en la fecha.
        zona = self._iom_param('iom_timezone_offset', '-05:00')
        fecha_emision = '{date}T00:00:00{offset}'.format(
            date=self.date,
            offset=zona,
        )

        return {
            'documento': {
                'codigoSucursalEmisor': self._iom_param('iom_sucursal', '0001'),
                'tipoSucursal': self._iom_param('iom_tipo_sucursal', '1'),
                'datosTransaccion': {
                    'tipoEmision': self._iom_param('iom_tipo_emision', '01'),
                    'tipoDocumento': self._iom_param('iom_tipo_documento', '01'),
                    'numeroDocumentoFiscal': str(self.sequence_number).zfill(10),
                    'puntoFacturacionFiscal': self._iom_param(
                        'iom_punto_fiscal', '001'
                    ),
                    'fechaEmision': fecha_emision,
                    'naturalezaOperacion': self._iom_param(
                        'iom_naturaleza_operacion', '01'
                    ),
                    'tipoOperacion': self._iom_param('iom_tipo_operacion', '1'),
                    'destinoOperacion': self._iom_param(
                        'iom_destino_operacion', '1'
                    ),
                    'formatoCAFE': '1',
                    'entregaCAFE': '1',
                    'envioContenedor': '1',
                    'procesoGeneracion': '1',
                    'tipoVenta': '1',
                    'cliente': self._iom_build_cliente(self.partner_id),
                },
                'listaItems': items,
                'totalesSubTotales': {
                    'totalPrecioNeto': '%.2f' % suma_neto,
                    'totalITBMS': '%.2f' % suma_impuesto,
                    'totalISC': self._iom_param('iom_total_isc', '0.00'),
                    'totalMontoGravado': '%.2f' % suma_neto,
                    'totalDescuento': '0.00',
                    'totalAcarreoCobrado': '0.00',
                    'valorSeguroCobrado': '0.00',
                    'totalFactura': '%.2f' % self.amount_total,
                    'totalValorRecibido': '%.2f' % self.amount_total,
                    'tiempoPago': tiempo_pago,
                    'nroItems': str(len(items)),
                    'totalTodosItems': '%.2f' % suma_total,
                    'listaFormaPago': [
                        {
                            'formaPagoFact': forma_pago,
                            'descFormaPago': ' ',
                            'valorCuotaPagada': '%.2f' % self.amount_total,
                        }
                    ],
                },
            }
        }

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    @staticmethod
    def _iom_datos_autorizacion(data):
        """Saca CUFE/QR/protocolo de la respuesta del provider.

        El middleware hace pass-through, asi que la forma depende de cada
        provider. Se buscan varias rutas en lugar de asumir una sola.
        """
        return {
            'cufe': IOMClient._first(
                data, 'cufe', 'datosEnvio.cufe', 'documento.cufe', 'respuesta.cufe'
            ) or '',
            'qr': IOMClient._first(
                data, 'qr', 'datosEnvio.qr', 'documento.qr', 'respuesta.qr'
            ) or '',
            'protocolo': IOMClient._first(
                data, 'protocolo', 'datosEnvio.protocolo', 'respuesta.protocolo'
            ) or '',
            'fecha_aceptacion': IOMClient._first(
                data,
                'fechaRecepcionDGI',
                'datosEnvio.fechaRecepcionDGI',
                'respuesta.fechaRecepcionDGI',
            ),
        }

    def _iom_emitir_una(self, client):
        """Emite una sola factura.

        Devuelve (resultado, mensaje) donde resultado es:

        * ``aceptado``: EBI autorizo el documento.
        * ``omitida``: no correspondia emitirla (ya enviada, no confirmada,
          o no es una factura de venta). No es un error.
        * ``error``: los datos no permiten armar el payload, o EBI rechazo.
        """
        if self.iom_estado_dte in ('enviando', 'aceptado'):
            return 'omitida', _('La factura %s ya fue enviada.', self.name)

        if self.state != 'posted':
            return 'omitida', _(
                'La factura %s esta en borrador. Confirmala antes de emitir.', self.name
            )

        if self.move_type != 'out_invoice':
            return 'omitida', _(
                'La factura %s no es una factura de venta.', self.name
            )

        try:
            payload = self._iom_build_payload()
        except UserError as error:
            return 'error', str(error)

        self.write({
            'iom_estado_dte': 'enviando',
            'iom_fecha_envio': fields.Datetime.now(),
        })

        try:
            data = client.emit(payload)
        except IOMError as error:
            self.write({
                'iom_estado_dte': 'rechazado',
                'iom_respuesta': str(error),
            })
            return 'error', _('EBI rechazo %s: %s', self.name, error)

        datos = self._iom_datos_autorizacion(data)
        self.write({
            'iom_estado_dte': 'aceptado',
            'iom_cufe': datos['cufe'],
            'iom_qr': datos['qr'],
            'iom_protocolo': datos['protocolo'],
            'iom_fecha_aceptacion': datos['fecha_aceptacion'] or False,
            'iom_respuesta': str(data),
        })
        return 'aceptado', ''

    def action_iom_emitir(self):
        """Emite las facturas seleccionadas ante EBI-PAC via el middleware.

        Para una sola factura. Si alguna falla se detiene todo el lote, que es
        el comportamiento correcto para el boton del formulario.
        """
        client = IOMClient(self.env)

        for move in self:
            resultado, mensaje = move._iom_emitir_una(client)
            if resultado != 'aceptado':
                raise UserError(mensaje)

        return True

    def action_iom_emitir_lote(self):
        """Emite varias facturas isolando los fallos.

        Pensado para acciones de servidor y para el cron: una factura con
        datos incompletos no debe impedir que las demas salgan. Cada factura
        se procesa en su propio savepoint para que un error de validacion no
        revierta el estado de las ya emitidas.

        Distingue tres resultados: aceptadas, omitidas (no correspondia
        emitirlas) y con error. Solo el ultimo grupo es un problema real.
        """
        client = IOMClient(self.env)
        emitidas = []
        omitidas = []
        fallidas = []

        for move in self:
            try:
                with self.env.cr.savepoint():
                    resultado, mensaje = move._iom_emitir_una(client)
            except Exception as error:  # noqa: BLE001 - se registra y se sigue
                resultado, mensaje = 'error', str(error)
            if resultado == 'aceptado':
                emitidas.append(move.name)
            elif resultado == 'omitida':
                omitidas.append(mensaje)
            else:
                fallidas.append(mensaje)

        if not emitidas and not fallidas:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Emision EBI'),
                    'message': _(
                        'No se emitio ninguna factura nueva. Omitidas: %s.',
                        len(omitidas),
                    ),
                    'type': 'info',
                    'sticky': False,
                },
            }

        partes = [_('Emitidas: %s', ', '.join(emitidas))]
        if omitidas:
            partes.append(_('Omitidas: %s', len(omitidas)))
        if fallidas:
            partes.append(_('Con error: %s', len(fallidas)))

        detalle = '\n'.join('- %s' % m for m in fallidas + omitidas)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': (
                    _('Emision EBI incompleta') if fallidas
                    else _('Emision EBI completa')
                ),
                'message': '%s\n\n%s' % ('. '.join(partes), detalle),
                'type': 'warning' if fallidas else 'success',
                # El aviso queda pegado si hubo errores, para que no se pierda
                # en el scroll de notificaciones.
                'sticky': bool(fallidas),
            },
        }

    def action_iom_anular(self):
        """Anula las facturas ya aceptadas ante EBI-PAC."""
        client = IOMClient(self.env)

        for move in self:
            if move.iom_estado_dte != 'aceptado':
                raise UserError(
                    _('La factura %s no esta aceptada por DGI.', move.name)
                )
            if not move.iom_cufe:
                raise UserError(
                    _('La factura %s no tiene CUFE registrado.', move.name)
                )

            payload = {
                'documento': {
                    'tipoDocumento': self._iom_param('iom_tipo_documento', '01'),
                    'numeroDocumentoFiscal': str(move.sequence_number).zfill(10),
                    'puntoFacturacionFiscal': self._iom_param(
                        'iom_punto_fiscal', '001'
                    ),
                    'codigoSucursalEmisor': self._iom_param('iom_sucursal', '0001'),
                    'cufe': move.iom_cufe,
                }
            }

            try:
                data = client.cancel(payload)
            except IOMError as error:
                move.write({'iom_respuesta': str(error)})
                raise UserError(
                    _('EBI rechazo anular %s: %s', move.name, error)
                ) from error

            move.write({
                'iom_estado_dte': 'anulado',
                'iom_respuesta': str(data),
            })

        return True

    def action_iom_ver_folios(self):
        """Muestra los folios disponibles en EBI para este cliente."""
        client = IOMClient(self.env)
        try:
            data = client.folios()
        except IOMError as error:
            raise UserError(_('No se pudieron leer los folios: %s', error)) from error
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Folios EBI'),
                'message': str(data),
                'type': 'info',
                'sticky': False,
            },
        }
