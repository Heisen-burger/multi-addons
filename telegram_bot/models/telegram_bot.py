# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
import secrets

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

API_URL = 'https://api.telegram.org/bot%s/%s'


class TelegramBot(models.AbstractModel):
    """Thin Bot API client. Other modules extend `_commands` and reuse `_send`."""
    _name = 'telegram.bot'
    _description = "Telegram Bot Client"

    @api.model
    def _param(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param('telegram_bot.' + key, default)

    @api.model
    def _call(self, method, **payload):
        """POST one Bot API method. Tests patch this method.

        Errors are logged, never raised: a broken send must not roll back the caller's
        transaction or make Telegram retry the webhook.
        """
        token = self._param('bot_token')
        if not token:
            _logger.warning("Telegram: no bot token configured, %s skipped", method)
            return {}
        try:
            response = requests.post(API_URL % (token, method), json=payload, timeout=10)
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            _logger.warning("Telegram %s failed: %s", method, error)
            return {}
        if not data.get('ok'):
            _logger.warning("Telegram %s refused: %s", method, data.get('description'))
            if data.get('error_code') == 403 and payload.get('chat_id'):
                # user blocked the bot: stop sending
                self.env['telegram.chat'].search([('chat_id', '=', payload['chat_id'])]).write({'active': False})
        return data

    @api.model
    def _send(self, chat_id, text, keyboard=None, reply_keyboard=None):
        """sendMessage in HTML mode. `keyboard` is a list of inline button rows."""
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                   'link_preview_options': {'is_disabled': True}}
        if keyboard:
            payload['reply_markup'] = {'inline_keyboard': keyboard}
        elif reply_keyboard:
            payload['reply_markup'] = reply_keyboard
        return self._call('sendMessage', **payload)

    @api.model
    def _fmt_dt(self, value, tz=None):
        if not value:
            return ""
        record = self.with_context(tz=tz) if tz else self
        return fields.Datetime.context_timestamp(record, value).strftime('%d/%m %H:%M')

    @api.model
    def _commands(self):
        """[(command, description)] shown by /help and registered with setMyCommands.

        Extensions call super() and append their own.
        """
        return [
            ('start', _("Start")),
            ('help', _("Help")),
        ]

    @api.model
    def action_register_webhook(self):
        params = self.env['ir.config_parameter'].sudo()
        secret = self._param('webhook_secret')
        if not secret:
            secret = secrets.token_urlsafe(32)
            params.set_param('telegram_bot.webhook_secret', secret)
        url = params.get_param('web.base.url').rstrip('/') + '/telegram_bot/webhook'
        hook = self._call('setWebhook', url=url, secret_token=secret,
                          allowed_updates=['message', 'callback_query'])
        self._call('setMyCommands', commands=[{'command': c, 'description': d} for c, d in self._commands()])
        info = self._call('getWebhookInfo').get('result', {})
        message = _("Webhook: %(url)s\nPending updates: %(pending)s\nLast error: %(error)s",
                    url=info.get('url') or url, pending=info.get('pending_update_count', 0),
                    error=info.get('last_error_message') or "-")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Telegram webhook registered") if hook.get('ok') else _("Telegram webhook failed"),
                'message': message,
                'type': 'success' if hook.get('ok') else 'danger',
                'sticky': True,
            },
        }
