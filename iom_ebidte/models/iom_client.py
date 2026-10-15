import json
import logging

import requests

_logger = logging.getLogger(__name__)


class IOMError(Exception):
    """Error de negocio devuelto por el middleware o por EBI."""


class IOMClient:
    """Cliente HTTP del middleware IOM.

    Solo se usa desde codigo Python del lado servidor, donde `requests` si
    esta disponible. Las credenciales se leen de los parametros del sistema
    y nunca viajan al navegador.
    """

    def __init__(self, env):
        self.env = env
        params = env['ir.config_parameter'].sudo()
        self.base_url = (params.get_param('iom_url') or '').rstrip('/')
        self.api_key = params.get_param('iom_api_key') or ''
        self.timeout = int(params.get_param('iom_timeout') or 60)

        if not self.base_url:
            raise IOMError('Parametro iom_url no configurado.')
        if not self.api_key:
            raise IOMError('Parametro iom_api_key no configurado.')

    def _post(self, path, payload):
        url = f'{self.base_url}{path}'
        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
        }
        try:
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise IOMError(
                f'No se pudo conectar al middleware IOM en {url}: {error}'
            ) from error

        if response.status_code >= 400:
            raise IOMError(
                f'El middleware IOM respondio HTTP {response.status_code}: {response.text[:500]}'
            )

        try:
            return response.json()
        except ValueError as error:
            raise IOMError(
                f'El middleware IOM devolvio una respuesta no JSON: {response.text[:500]}'
            ) from error

    @staticmethod
    def _first(data, *paths):
        """Devuelve el primer valor no vacio entre rutas `a.b.c`."""
        for path in paths:
            actual = data
            for parte in path.split('.'):
                if not isinstance(actual, dict):
                    actual = None
                    break
                actual = actual.get(parte)
            if actual not in (None, '', [], {}):
                return actual
        return None

    @staticmethod
    def _es_exitoso(data):
        """El middleware es pass-through: cada provider devuelve su propio
        formato. Se aceptan las variantes conocidas en lugar de asumir una.
        """
        # Variante EBI: {"codigo": "200", "mensaje": ...}
        codigo = IOMClient._first(data, 'codigo', 'respuesta.codigo')
        if codigo is not None:
            return str(codigo) in ('200', '0', 'OK', 'ok')

        # Variante MOCK / passthrough generico: {"status": "ok"}
        estado = IOMClient._first(data, 'status', 'estado', 'exito')
        if isinstance(estado, bool):
            return estado
        if estado is not None:
            return str(estado).lower() in ('ok', 'exito', 'exitoso', 'true', '200')

        # Sin marcador de estado: si hay documento aceptado, es un exito.
        return IOMClient._first(data, 'cufe', 'datosEnvio.cufe', 'documento.cufe') is not None

    @staticmethod
    def _error_legible(data):
        return IOMClient._first(
            data, 'mensaje', 'message', 'error', 'respuesta.mensaje', 'respuesta'
        )

    def emit(self, payload):
        """Emite el documento.

        El exito no se decide por el HTTP status (el middleware devuelve 201):
        se delega en el cuerpo de la respuesta del provider.
        """
        data = self._post('/billing/emit', payload)

        if not self._es_exitoso(data):
            raise IOMError(str(self._error_legible(data) or json.dumps(data)[:500]))

        return data

    def cancel(self, payload):
        data = self._post('/billing/cancel', payload)
        if not self._es_exitoso(data):
            raise IOMError(str(self._error_legible(data) or json.dumps(data)[:500]))
        return data

    def folios(self):
        url = f'{self.base_url}/billing/folios'
        try:
            response = requests.get(
                url,
                headers={'x-api-key': self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise IOMError(f'No se pudo consultar folios: {error}') from error

        if response.status_code >= 400:
            raise IOMError(
                f'La consulta de folios devolvio HTTP {response.status_code}: {response.text[:500]}'
            )
        return response.json()
