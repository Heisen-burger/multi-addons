# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Turn the single configured bot into a telegram.bot record and attach every chat to it.

    The old settings lived in ir.config_parameter (telegram_bot.bot_token, webhook_secret,
    access_code, welcome). The webhook URL changed too: register it again from the bot form.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter']
    token = params.get_param('telegram_bot.bot_token')
    if not token:
        return
    bot = env['telegram.bot'].create({
        'name': "Bot",
        'token': token,
        'webhook_secret': params.get_param('telegram_bot.webhook_secret') or False,
        'access_code': params.get_param('telegram_bot.access_code') or False,
        'welcome': params.get_param('telegram_bot.welcome') or False,
    })
    cr.execute("UPDATE telegram_chat SET bot_id = %s WHERE bot_id IS NULL", (bot.id,))
    for key in ('bot_token', 'webhook_secret', 'access_code', 'welcome'):
        params.search([('key', '=', 'telegram_bot.' + key)]).unlink()
