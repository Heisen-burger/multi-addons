# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "Telegram Bot",
    'summary': "Telegram Bot API client, webhook and command routing for other modules to extend",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.1.0.1',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/telegram_chat_views.xml',
        'views/res_config_settings_views.xml',
        'data/ir_actions_server.xml',
    ],
}
