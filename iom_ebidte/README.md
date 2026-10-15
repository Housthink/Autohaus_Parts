# iom_ebidte

Emision de facturas ante EBI-PAC (Panama) a traves del middleware IOM.

Como funciona
-------------

El modulo corre **todo en el servidor de Odoo**. No usa ``act_url``, ni botones
con JavaScript, ni expone la API key al navegador.

#. El boton "Emitir a EBI" en la factura llama a ``action_iom_emitir``.
#. Ese metodo arma el payload EBI en Python (``_iom_build_payload``).
#. ``IOMClient`` hace un ``POST /billing/emit`` al middleware con la API key.
#. La respuesta se guarda en la factura: CUFE, QR, protocolo y fecha de DGI.

El endpoint ``GET /iom/emit?move_id=<id>`` hace lo mismo desde el navegador y
sirve para reintentos manuales. Tambien corre en Python del servidor, asi que
la API key sigue sin salir.

Como dispararla
---------------

Hay tres caminos. Todos comparten el mismo nucleo (``_iom_emitir_una``), asi
que las reglas de validacion y los estados guardados son identicos.

Boton "Emitir ante EBI" en la factura

Es la opcion para el dia a dia. Actua sobre una sola factura, es rapida y
entra en detalle: si algo falla, la excepcion muestra el motivo exacto y la
factura se queda en ``borrador``.

Accion de servidor "IOM: Emitir a EBI (factura actual)"

Va en el menu Acciones. Es la misma logica del boton pero pensada para
listas: si se seleccionan varias facturas y una falla, **se detiene en la
primera** y las siguientes no se tocan. Es comodo para reintentar un grupo
pequeno que se sabe que esta bien.

Accion de servidor "IOM: Emitir a EBI (lote)"

Tambien acepta varias facturas, pero aqui cada una se procesa aislada con un
savepoint. Una factura invalida no frena a las demas: al final avisa cuantas
quedaron aceptadas, cuantas se omitieron por ya estar autorizadas y cuantas
fallaron, con el detalle de cada error.

Es la recomendada para lotes. Medido con el cliente MOCK: 2 validas + 2
invalidas en 0.08 s, con las dos buenas aceptadas y las dos malas sin tocar.

Cron "IOM: Emitir a EBI las pendientes"

Solo recoge facturas ``posted``, de cliente (``out_invoice``) y en estado
``borrador``. Se entrega **inactivo**: hay que activarlo a mano en
Ajustes > Tecnico > Automatizar > Acciones planificadas.

Importante: el cron no reintenta las facturas rechazadas. Para que una factura
vuelva a entrar al circuito hay que corregir el motivo y pasarla de nuevo a
``borrador``; de lo contrario el cron la ignorara para siempre. Tampoco
conviene activarlo sin antes revisar el lote a mano, porque cualquier factura
en ``borrador`` se emite sin supervision.

Resumen

* Una factura -> boton de la factura.
* Varias y quiero que pare si algo falla -> accion individual.
* Varias y quiero que continue pase lo que pase -> accion de lote.
* Sin supervision -> cron, activo y con la regla de reintento entendida.

Instalacion
------------

#. Configurar la URL del middleware en Ajustes > Contabilidad > Configuracion >
   Facturacion IOM / EBI.
#. Poner ``iom_api_key`` con la key del cliente en el middleware.
#. ``iom_url`` debe ser alcanzable desde el servidor de Odoo. Si Odoo esta
   en la nube, ``localhost`` no sirve: hay que exponer el middleware con una URL
   publica o una VPN.

Campos agregados en ``account.move``

* ``iom_estado_dte``: borrador, enviando, aceptado, rechazado, anulado
* ``iom_cufe``: codigo de verificacion de la DGI
* ``iom_qr``: QR para consulta publica
* ``iom_protocolo``: protocolo de aceptacion
* ``iom_fecha_envio``: momento del envio
* ``iom_fecha_aceptacion``: ``fechaRecepcionDGI`` informado por EBI
* ``iom_respuesta``: JSON crudo de la respuesta

Parametros del sistema

* ``iom_url``: vacio. Base del middleware.
* ``iom_api_key``: vacio. Key del cliente en el middleware.
* ``iom_sucursal``: ``0001``.
* ``iom_punto_fiscal``: ``001``. Asignado por EBI.
* ``iom_tipo_documento``: ``01``. 01 factura, 02 nota debito, 03 nota credito.
* ``iom_tipo_contribuyente``: ``2``. 1 natural, 2 juridico.
* ``iom_codigo_ubicacion``: ``1-1-1``.
* ``iom_tipo_cliente``: vacio. 01 contribuyente, 02 consumidor final,
  03 gobierno, 04 extranjero. Si esta vacio se deduce del RUC del contacto.
* ``iom_unidad_medida_defecto``: ``UND``. Codigo de la Tabla 3 de EBI.
* ``iom_corregimiento``: vacio. Si vacio usa el distrito del contacto.
* ``iom_timezone_offset``: ``-05:00``.
* ``iom_timeout``: ``60``. Segundos.

Nota sobre el ITBMS
--------------------

El codigo ITBMS se deriva del porcentaje calculado sobre los importes de la
linea, no de ``tax_group_id``. Odoo 19 no expone ``tax_group_type`` en
``account.tax.group``, y calcularlo asi evita depender de ese campo.

Catalogo: ``00`` exento, ```01``` 7%, ``02`` 10%, ``03`` 15%.

Campos agregados en ``product.product``

* ``iom_unidad_medida``: codigo de unidad segun la Tabla 3 de EBI. Si esta
  vacio se usa ``iom_unidad_medida_defecto``.

Reglas del receptor (docs EBI /api/Enviar)
-------------------------------------------

* ``01`` contribuyente y ``03`` gobierno exigen RUC, digito verificador (2
  digitos), razon social y provincia/distrito/corregimiento. Si falta algo el
  modulo lanza error antes de llamar al middleware.
* ``02`` consumidor final: el RUC es opcional y no se manda digito verificador.
  Es el tipo que se deduce cuando el contacto no tiene RUC.
* ``04`` extranjero: todavia no soportado, porque exige tipo de identificacion
  y numero de identificacion del extranjero.
* ``tipoClienteFE`` se puede forzar con ``iom_tipo_cliente``; si se deja vacio
  se deduce: con RUC => 01, sin RUC => 02.

Pendiente de confirmar con EBI
------------------------------

* Los codigos de la Tabla 3 (unidades de medida). Se usa ``UND`` por defecto y
  se puede cambiar por linea en el producto.
* Como devuelve EBI el CUFE, QR, protocolo y ``fechaRecepcionDGI``. El modulo
  busca esos datos en varias rutas de la respuesta, asi que funciona con
  cualquier variante, pero conviene ajustarlo a la real.
