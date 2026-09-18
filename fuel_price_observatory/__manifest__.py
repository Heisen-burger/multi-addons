# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "Fuel Price Observatory",
    'summary': "Italian fuel prices from the MIMIT observatory: history, min/max, change alerts",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.1.0.2',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/fuel_station_fuel_views.xml',
        'views/fuel_station_views.xml',
        'views/fuel_price_views.xml',
        'views/menus.xml',
        'data/mail_message_subtype.xml',
        'data/ir_actions_server.xml',
        'data/ir_cron.xml',
    ],
}
