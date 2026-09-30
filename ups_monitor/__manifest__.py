# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "UPS Monitor",
    'summary': "UPS telemetry pushed by a Raspberry Pi: charts, mains outages, events",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.1.2.0',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/ups_device_views.xml',
        'views/ups_sample_views.xml',
        'views/ups_outage_views.xml',
        'views/ups_event_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ups_monitor/static/src/dashboard/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
}
