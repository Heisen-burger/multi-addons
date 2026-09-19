# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "Fuel Price Telegram Bot",
    'summary': "Telegram bot: nearest fuel prices, subscriptions with thresholds, change alerts",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.1.0.0',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['telegram_bot', 'fuel_price_observatory'],
    'data': [
        'security/ir.model.access.csv',
        'views/telegram_chat_views.xml',
        'views/telegram_subscription_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
}
