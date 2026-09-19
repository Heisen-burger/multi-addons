# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    telegram_bot_token = fields.Char("Telegram Bot Token", config_parameter='telegram_bot.bot_token',
                                     help="Token given by @BotFather.")
    telegram_webhook_secret = fields.Char("Telegram Webhook Secret", config_parameter='telegram_bot.webhook_secret',
                                          help="Generated on webhook registration when empty.")
    telegram_welcome = fields.Char("Telegram Welcome Message", config_parameter='telegram_bot.welcome',
                                   help="Answer to /start. Modules can override it in code.")
