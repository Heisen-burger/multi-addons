# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
{
    'name': "Telegram Media Download Bot",
    'summary': "Telegram bot that turns a track link into an MP3; one provider per site, Suno included",
    'license': 'OPL-1',
    'author': "STeSI Consulting",
    'category': 'Tools',
    'version': '19.0.1.2.0',
    'website': "https://github.com/Heisen-burger/multi-addons",
    'depends': ['telegram_bot', 'base_setup'],
    'external_dependencies': {'bin': ['ffmpeg']},
    'data': [
        'security/ir.model.access.csv',
        'views/media_download_views.xml',
        'views/res_config_settings_views.xml',
        'data/ir_actions_server.xml',
    ],
}
