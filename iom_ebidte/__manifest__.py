{
    "name": "IOM EBI DTE",
    "version": "19.0.1.0.3",
    "author": "AutoHaus Parts",
    "category": "Accounting",
    "summary": "Emision de facturas ante EBI-PAC a traves del middleware IOM",
    "depends": ["account"],
    "data": [
        "data/ir_actions_server.xml",
        "views/account_move_views.xml",
        "views/res_config_settings_views.xml",
        "views/templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
