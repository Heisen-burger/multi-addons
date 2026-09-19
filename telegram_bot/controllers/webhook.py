# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from werkzeug.exceptions import Forbidden

from odoo import SUPERUSER_ID, http
from odoo.http import request

SECRET_HEADER = 'X-Telegram-Bot-Api-Secret-Token'


class TelegramWebhook(http.Controller):
    # auth='none' defaults to a read-only cursor and env.uid None: force both
    @http.route('/telegram_bot/webhook/<int:bot_id>', type='json2', auth='none', methods=['POST'],
                csrf=False, readonly=False)
    def webhook(self, bot_id, **update):
        env = request.env(user=SUPERUSER_ID, su=True)
        bot = env['telegram.bot'].browse(bot_id).exists()
        secret = bot.webhook_secret if bot else None
        if not secret or request.httprequest.headers.get(SECRET_HEADER) != secret:
            raise Forbidden()
        bot._handle_update(update)
        # always 200: Telegram retries any other status forever
        return {}
