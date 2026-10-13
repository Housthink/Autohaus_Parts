# Guion rapido del proyecto FinditParts (hp-finditpartsV19)

Este archivo resume la funcion de cada carpeta y script para que otra IA o persona entienda rapido que hace el codigo. Todo el contenido esta en ASCII y en castellano sin tildes para facilitar copiado.

## Idea general
- Modulo de Odoo 19 llamado `finditparts_integration` que conecta con la API de FindinPart para traer catalogo, existencias, precios y pedidos, y crear/actualizar productos y ordenes dentro de Odoo.
- Incluye scripts de linea de comandos para probar la API, sincronizar productos y verificar que el modulo esta bien instalado.
- Hay varios JSON de ejemplo y resultados de pruebas que sirven como muestras de payloads y respuestas reales.

## Modulo Odoo: carpeta `finditparts_integration/`
- `__manifest__.py`: metadatos del modulo (nombre, version, dependencias Odoo como product/stock/sale, menus y vistas cargadas, dependencias externas como requests y Pillow).
- `__init__.py` y `models/__init__.py`: exponen modelos al cargar el modulo.
- Modelos:
  - `models/finditparts_config.py`: modelo `finditparts.config` con la configuracion de API (base URL, credenciales JWT, intervalos de sincronizacion, opciones de autopublicacion y actualizacion de stock/precios). Incluye botones para probar conexion y actualizar el cron interno.
  - `models/finditparts_product.py`: modelo `finditparts.product` que almacena datos del API (SKU, marca, descripciones, precios, stock, imagenes, compatibilidad). Contiene logica para crear/actualizar el registro en Odoo (`sync_to_odoo`), construir descripcion HTML rica solo para web (`website_description`/`long_description` con Quick Facts, galeria, PIES, atributos e interchanges) y mantener `description_sale` en texto plano para SO/Facturas, calcular precios de venta/costo y sincronizar lotes desde la API (`sync_products_from_api`). Usa `FindinPartAPIClient`.
  - `models/finditparts_order.py`: modelo `finditparts.order` y `finditparts.order.line` para representar pedidos traidos de FindinPart y generar `sale.order` en Odoo. Maneja estados draft/confirmed/processing/shipped/delivered/cancelled y enlaza con partner y productos Odoo.
  - `models/finditparts_sync_wizard.py`: wizard transitorio `finditparts.product.sync.wizard` para lanzar sincronizaciones manuales (por busqueda, por numero de parte o lote limitado), mostrar resultados y navegar a los productos creados.
  - `models/finditparts_sync_cron.py`: programador de sincronizaciones `finditparts.sync.cron` que guarda una configuracion (tipo: search/part_number/all, query/part_number/limit, cron_expression estilo crontab) y crea un `ir.cron` ligado para ejecutar `sync_products_from_api` con esos parametros. Guarda ultimo resultado/fecha y permite editar/eliminar crones vinculados.
- Utils:
  - `utils/api_client.py`: cliente HTTP para la API FindinPart. Genera JWT HMAC, maneja cabeceras y session, ofrece metodos de busqueda (por query, part number, categorias, marcas), paginacion generadora, obtencion de imagenes, precios, inventario, y helpers para ordenar/paginar. Usado por modelos y scripts CLI.
- Seguridad y datos:
  - `security/finditparts_security.xml`: define grupos `FindinPart User` y `FindinPart Manager`.
  - `security/ir.model.access.csv`: permisos de lectura/escritura/creacion/borrado para usuarios base en los modelos del modulo (todos en modo abierto).
  - `data/finditparts_data.xml`: datos iniciales (categorias de productos base y un proveedor `FinditParts API`).
  - `demo/finditparts_demo.xml`: datos demo (configuracion, productos de ejemplo, cliente y pedido ficticio).
- Vistas (carpeta `views/`):
  - `finditparts_config_views.xml`: formulario y lista para configurar credenciales y opciones; boton "Test Connection".
  - `finditparts_product_views.xml`: formulario con pestañas de descripcion, especificaciones y compatibilidad; lista y filtros por stock/sync; accion de menu.
  - `finditparts_order_views.xml`: formulario, lista y busqueda para pedidos con statusbar; permite ver tracking y totales.
  - `finditparts_sync_wizard_views.xml`: vista del wizard de sincronizacion con botones para iniciar sync y ver productos creados.
  - `finditparts_cron_views.xml`: formulario/arbol/busqueda para crear crones de sincronizacion (campos sync_type, query/part_number, limit, cron_expression) y ver el `ir.cron` vinculado, siguiente ejecucion y ultimo resultado. Tiene filtros en la vista de busqueda para tipo de sync (search/part_number/all) y para estado activo/inactivo, mas agrupaciones por sync_type y active. Menu "Sync Crons" bajo FindinPart.
  - `menu_views.xml`: menus de aplicacion FindinPart (Configuracion, Sync Products, Products, Orders) con icono `static/description/icon.png`.
- Recursos estaticos:
  - `static/description/icon.png`: icono usado en el menu y la app.

## Scripts y herramientas en la raiz
- `sync_products_from_api.py`: script CLI para sincronizar productos fuera de la interfaz de Odoo. Inicializa el entorno Odoo via `odoo.registry`, llama a `finditparts.product.sync_products_from_api` y guarda resultados en `sync_results_YYYYMMDD_HHMMSS.json`. Permite buscar por texto, numero de parte, leer de archivo JSON o traer lotes limitados.
- `test_api_simple.py`: prueba rapida que genera un JWT y hace varias peticiones GET (lista, busqueda, lookup, producto especifico). Imprime detalle de descripciones, imagenes y atributos para verificar conectividad.
- `test_all_endpoints.py`: recorre los endpoints principales del Postman collection (busquedas, lookup, multi producto, PIES) y muestra estados HTTP.
- `test_product_creation.py`: valida estructura de los JSON de ejemplo (`producto_completo_ejemplo.json`, `ui_product_example.json`) e imprime campos clave; muestra comandos para sincronizar.
- `verificar_instalacion.py`: checklist post-instalacion (estructura de modulo, `api_config.json`, scripts de prueba, archivos de ejemplo) y lista pasos siguientes para el cliente.
- `install_module.sh`: script interactivo para copiar el modulo al directorio de addons, ajustar permisos y recordar reiniciar Odoo. Llama a `test_module.py` y `test_api.py` si existieran (no estan incluidos), por lo que pueden omitirse o ajustarse.
- `install_and_test.sh`: guia paso a paso (echo) para copiar el modulo, instalar dependencias, reiniciar Odoo, configurar credenciales y ejecutar pruebas rapidas.
- `requirements.txt`: dependencias Python minimas (requests, Pillow, python-dateutil) pensadas para el entorno Odoo.
- `api_config.json`: ejemplo de configuracion JWT/base_url usada por los scripts de prueba.
- `sync_products.log`: log generado por sincronizaciones anteriores (registrado por `sync_products_from_api.py`).
- Otros JSON de referencia:
  - `producto_completo_ejemplo.json`, `producto_real_ejemplo.json`: payloads completos de productos devueltos por la API (sirven para pruebas offline).
  - `ui_product_example.json`, `ui_product_simplified.json`: ejemplos simplificados para UI o testing.
  - `sync_results_complete.json`, `client_brands_test_results.json`, `marcas_principales_analisis.json`: resultados de pruebas previas y analisis por marcas.
  - `api_config.json` (ya mencionado) y `sync_results_*` generados por scripts.
- `README.md`: por ahora solo contiene el titulo; puede ampliarse usando este resumen.

## Flujo basico de integracion
- Configurar `finditparts.config` en Odoo (o via `api_config.json` para scripts) con base URL y credenciales JWT.
- Probar la API con `test_api_simple.py` o el boton "Test Connection" en el formulario de configuracion.
- Sincronizar productos:
  - Desde Odoo: menu FindinPart -> Sync Products (wizard `finditparts.product.sync.wizard`).
  - Desde CLI: `python3 sync_products_from_api.py --search "texto"` o `--part-number CODE`.
- Cada producto se guarda en `finditparts.product`, se sincroniza a `product.template` (creacion o actualizacion), asigna categoria, precio, stock y opcionalmente descarga imagen.
- Pedidos traidos o creados pueden reflejarse en `finditparts.order` y convertirse en `sale.order` segun la configuracion.

## Notas rapidas para otras IAs
- La logica central de negocio esta en `finditparts_integration/models/finditparts_product.py` y `utils/api_client.py`.
- Los scripts de instalacion mencionan utilidades que no estan en el repo (`test_module.py`, `test_api.py`); ignorarlos o reemplazarlos por `verificar_instalacion.py` y `test_api_simple.py`.
- Todo el modulo asume Odoo 19 y usa dependencias nativas de Odoo (product, stock, sale, account, website_sale, mail). Ajustar nombres de campos tipo product.template si se porta a versiones diferentes.
