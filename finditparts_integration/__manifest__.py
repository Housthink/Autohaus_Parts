{
    'name': 'FindinPart API Integration',
    'version': '19.0.1.6.0',
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
        'views/res_config_settings_views.xml',
        'views/website_product_templates.xml',
        'views/website_checkout_override.xml',
        'views/website_header_override.xml',
        'views/website_footer_override.xml',
        'views/website_shop_hero.xml',
        'views/website_shop_categories.xml',
        'views/website_topbar.xml',
        'views/website_product_layout.xml',
        'views/website_product_related.xml',
        'views/website_whatsapp_button.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'finditparts_integration/static/src/css/autohaus_header.css',
            'finditparts_integration/static/src/css/autohaus_footer.css',
            'finditparts_integration/static/src/css/autohaus_shop_hero.css',
            'finditparts_integration/static/src/css/autohaus_product.css',
            'finditparts_integration/static/src/css/autohaus_product_facts.css',
            'finditparts_integration/static/src/css/shop_products_chips.css',
            'finditparts_integration/static/src/css/autohaus_categories.css',
            'finditparts_integration/static/src/css/autohaus_whatsapp.css',
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
