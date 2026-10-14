{
    'name': 'FindinPart API Integration',
    'version': '19.0.1.1.0',
    'category': 'Inventory/Purchase',
    'summary': 'Integration with FindinPart API for diesel engine parts catalog and order management',
    'description': """
        Comprehensive integration module for FindinPart API that provides:
        - Product catalog synchronization (50,000+ SKUs)
        - Real-time stock and pricing updates
        - Order management and fulfillment
        - Automated inventory management
        - Customer order tracking
    """,
    'author': 'AutoHaus Parts',
    'website': 'https://www.finditparts.com',
    'depends': [
        'base',
        'product',
        'stock',
        'purchase',
        'sale',
        'account',
        'payment',
        'website_sale',
        'mail',
        'crm',
    ],
    'data': [
        'security/finditparts_security.xml',
        'security/ir.model.access.csv',
        'data/finditparts_data.xml',
        'views/finditparts_config_views.xml',
        'views/finditparts_product_views.xml',
        'views/finditparts_order_views.xml',
        'views/finditparts_sync_wizard_views.xml',
        'views/menu_views.xml',
        'views/finditparts_cron_views.xml',
        'views/website_product_templates.xml',
        'views/website_checkout_override.xml',
        'views/website_header_override.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'finditparts_integration/static/src/css/autohaus_header.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': [
            'requests',
            'pillow',
        ],
    },
}
