# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "Telegram Bot",
    'summary': "Telegram Bot API client, webhook and command routing for other modules to extend",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.2.0.1',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/telegram_bot_views.xml',
        'views/telegram_chat_views.xml',
    ],
}
