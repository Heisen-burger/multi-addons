# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
import secrets

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

API_URL = 'https://api.telegram.org/bot%s/%s'


class TelegramBot(models.Model):
    """One record per Telegram bot. `kind` picks the handler that runs the conversation."""
    _name = 'telegram.bot'
    _description = "Telegram Bot"
    _order = 'name, id'

    name = fields.Char(required=True)
    token = fields.Char(required=True, groups='base.group_system', help="Token given by @BotFather.")
    kind = fields.Selection([('generic', "Generic")], default='generic', required=True,
                            help="Conversation handler. Modules add kinds with selection_add.")
    webhook_secret = fields.Char(groups='base.group_system',
                                 help="Checked on every webhook call. Generated on registration when empty.")
    access_code = fields.Char(help="When set, a new chat must send '/start <code>' before the bot answers. "
                                   "Share the link t.me/<bot>?start=<code>. Empty: open to everyone.")
    welcome = fields.Text(help="Answer to /start for the generic handler.")
    username = fields.Char(readonly=True, help="Filled by the webhook registration (getMe).")
    webhook_url = fields.Char(compute='_compute_webhook_url')
    active = fields.Boolean(default=True)
    chat_ids = fields.One2many('telegram.chat', 'bot_id', string="Chats")
    chat_count = fields.Integer(compute='_compute_chat_count')

    _token_unique = models.Constraint(
        'unique (token)',
        "This bot token is already registered.",
    )

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for bot in self:
            bot.webhook_url = "%s/telegram_bot/webhook/%s" % (base, bot.id) if bot.id else False

    @api.depends('chat_ids')
    def _compute_chat_count(self):
        for bot in self:
            bot.chat_count = len(bot.chat_ids)

    def _handler(self):
        self.ensure_one()
        name = 'telegram.handler' if self.kind == 'generic' else 'telegram.handler.%s' % self.kind
        return self.env[name]

    # ------------------------------------------------------------------
    # Bot API
    # ------------------------------------------------------------------
    def _call(self, method, files=None, **payload):
        """POST one Bot API method (JSON, or multipart when `files` is given). Tests patch this.

        Errors are logged, never raised: a broken send must not roll back the caller's
        transaction or make Telegram retry the webhook.
        """
        self.ensure_one()
        token = self.sudo().token
        if not token:
            _logger.warning("Telegram bot %s: no token, %s skipped", self.name, method)
            return {}
        try:
            if files:
                response = requests.post(API_URL % (token, method), data=payload, files=files, timeout=120)
            else:
                response = requests.post(API_URL % (token, method), json=payload, timeout=10)
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            _logger.warning("Telegram %s failed: %s", method, error)
            return {}
        if not data.get('ok'):
            _logger.warning("Telegram %s refused: %s", method, data.get('description'))
            if data.get('error_code') == 403 and payload.get('chat_id'):
                # user blocked the bot: stop sending
                self.env['telegram.chat'].search(
                    [('bot_id', '=', self.id), ('chat_id', '=', payload['chat_id'])]).write({'active': False})
        return data

    def _send(self, chat_id, text, keyboard=None, reply_keyboard=None):
        """sendMessage in HTML mode. `keyboard` is a list of inline button rows."""
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                   'link_preview_options': {'is_disabled': True}}
        if keyboard:
            payload['reply_markup'] = {'inline_keyboard': keyboard}
        elif reply_keyboard:
            payload['reply_markup'] = reply_keyboard
        return self._call('sendMessage', **payload)

    FILE_METHODS = {
        'audio': ('sendAudio', 'audio', ('title', 'performer', 'duration')),
        'video': ('sendVideo', 'video', ('duration', 'width', 'height', 'supports_streaming')),
        'voice': ('sendVoice', 'voice', ('duration',)),
        'photo': ('sendPhoto', 'photo', ()),
        'document': ('sendDocument', 'document', ()),
    }

    def _send_file(self, chat_id, kind, data, filename, caption=None, **meta):
        """Upload `data` as multipart with the Bot API method matching `kind`
        (audio, video, voice, photo, document). Telegram caps bot uploads at 50 MB.
        `meta` holds the method's optional fields (title, performer, duration, ...)."""
        method, field, allowed = self.FILE_METHODS[kind]
        payload = {'chat_id': chat_id}
        for key in allowed:
            value = meta.get(key)
            if value not in (None, False, ''):
                payload[key] = int(value) if key in ('duration', 'width', 'height') else value
        if caption:
            payload['caption'] = caption
            payload['parse_mode'] = 'HTML'
        return self._call(method, files={field: (filename, data)}, **payload)

    def _send_audio(self, chat_id, data, filename, title=None, performer=None, duration=None, caption=None):
        return self._send_file(chat_id, 'audio', data, filename, caption=caption,
                               title=title, performer=performer, duration=duration)

    def _fmt_dt(self, value, tz=None):
        if not value:
            return ""
        record = self.with_context(tz=tz) if tz else self
        return fields.Datetime.context_timestamp(record, value).strftime('%d/%m %H:%M')

    # ------------------------------------------------------------------
    # webhook
    # ------------------------------------------------------------------
    def action_register_webhook(self):
        self.ensure_one()
        me = self.sudo()
        if not me.webhook_secret:
            me.webhook_secret = secrets.token_urlsafe(32)
        info_me = self._call('getMe').get('result', {})
        if info_me.get('username'):
            me.username = info_me['username']
        hook = self._call('setWebhook', url=self.webhook_url, secret_token=me.webhook_secret,
                          allowed_updates=['message', 'callback_query'])
        self._call('setMyCommands', commands=[{'command': c, 'description': d}
                                              for c, d in self._handler()._commands()])
        info = self._call('getWebhookInfo').get('result', {})
        message = _("Webhook: %(url)s\nPending updates: %(pending)s\nLast error: %(error)s",
                    url=info.get('url') or self.webhook_url, pending=info.get('pending_update_count', 0),
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

    def _handle_update(self, update):
        self.ensure_one()
        try:
            self._dispatch(update)
        except Exception:  # noqa: BLE001 - Telegram retries on error, log and move on
            _logger.exception("Telegram bot %s: update %s failed", self.name, update.get('update_id'))

    def _dispatch(self, update):
        Chat = self.env['telegram.chat']
        handler = self._handler()
        query = update.get('callback_query')
        message = update.get('message')
        if query:
            chat = Chat._get_chat(self, query['message']['chat'], query.get('from'))
            self._call('answerCallbackQuery', callback_query_id=query['id'])
            if chat._check_access():
                handler._on_callback(chat, query.get('data') or '', query['message'])
        elif message:
            chat = Chat._get_chat(self, message['chat'], message.get('from'))
            if not chat._check_access(message.get('text') or ''):
                return
            if message.get('location'):
                handler._on_location(chat, message['location'])
            elif message.get('text'):
                handler._on_text(chat, message['text'].strip())
