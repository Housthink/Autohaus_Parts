from odoo import http
from odoo.http import request

import json

from ..models.iom_client import IOMClient, IOMError


class IOMController(http.Controller):

    @http.route('/iom/emit', type='http', auth='user', methods=['GET'],
                csrf=False, website=False)
    def iom_emit(self, **kwargs):
        """Dispara la emision de la factura indicada desde el navegador.

        La API key nunca sale del servidor: este endpoint corre en Python del
        lado de Odoo y es el unico lugar donde se usa `requests`. El boton de
        la vista solo necesita llamar a esta ruta.
        """
        move_id = kwargs.get('move_id')
        if not move_id:
            return request.not_found()

        move = request.env['account.move'].browse(int(move_id))
        if not move.exists():
            return request.not_found()

        try:
            payload = move._iom_build_payload()
            client = IOMClient(request.env)
            data = client.emit(payload)
        except IOMError as error:
            move.write({
                'iom_estado_dte': 'rechazado',
                'iom_respuesta': str(error),
            })
            return request.render(
                'iom_ebidte.emit_result',
                {'error': True, 'message': str(error)},
            )

        move.write({
            'iom_estado_dte': 'aceptado',
            'iom_cufe': data.get('cufe', ''),
            'iom_qr': data.get('qr', ''),
            'iom_protocolo': data.get('protocolo', ''),
            'iom_fecha_aceptacion': data.get('fechaRecepcionDGI') or False,
            'iom_respuesta': json.dumps(data),
        })

        return request.render(
            'iom_ebidte.emit_result',
            {
                'error': False,
                'message': 'Factura %s aceptada.' % move.name,
                'cufe': data.get('cufe', ''),
            },
        )
