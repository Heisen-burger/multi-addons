# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
from html import escape

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class TelegramChat(models.Model):
    """One record per Telegram chat. Routes updates to `_cmd_<name>`, `_cb_<key>`,
    `_on_free_text` and `_on_location`, which extensions override or add."""
    _name = 'telegram.chat'
    _description = "Telegram Chat"
    _order = 'name, id'

    chat_id = fields.Integer("Telegram Chat ID", required=True, index=True)
    name = fields.Char(required=True)
    username = fields.Char()
    lang = fields.Char("Telegram Language")
    state = fields.Selection([('idle', "Idle")], default='idle', required=True,
                             help="Conversation state. Extensions add values with selection_add.")
    active = fields.Boolean(default=True)

    _chat_id_unique = models.Constraint(
        'unique (chat_id)',
        "This Telegram chat is already registered.",
    )

    # ------------------------------------------------------------------
    # entry points
    # ------------------------------------------------------------------
    @api.model
    def _handle_update(self, update):
        try:
            self._dispatch(update)
        except Exception:  # noqa: BLE001 - Telegram retries on error, log and move on
            _logger.exception("Telegram update %s failed", update.get('update_id'))

    @api.model
    def _dispatch(self, update):
        query = update.get('callback_query')
        message = update.get('message')
        if query:
            chat = self._get_chat(query['message']['chat'], query.get('from'))
            self._bot()._call('answerCallbackQuery', callback_query_id=query['id'])
            chat._on_callback(query.get('data') or '', query['message'])
        elif message:
            chat = self._get_chat(message['chat'], message.get('from'))
            if message.get('location'):
                chat._on_location(message['location'])
            elif message.get('text'):
                chat._on_text(message['text'].strip())

    @api.model
    def _get_chat(self, tg_chat, tg_from):
        """Find or create the chat record; any message revives an archived chat."""
        name = tg_chat.get('title') or ' '.join(
            part for part in (tg_chat.get('first_name'), tg_chat.get('last_name')) if part
        ) or str(tg_chat['id'])
        vals = {'chat_id': tg_chat['id'], 'name': name, 'username': tg_chat.get('username') or False,
                'lang': (tg_from or {}).get('language_code') or False, 'active': True}
        chat = self.with_context(active_test=False).search([('chat_id', '=', tg_chat['id'])], limit=1)
        if chat:
            changed = {key: value for key, value in vals.items() if chat[key] != value}
            if changed:
                chat.write(changed)
        else:
            chat = self.create(vals)
        return chat.with_context(lang=chat._odoo_lang())

    def _odoo_lang(self):
        self.ensure_one()
        code = (self.lang or '').split('-')[0]
        # the record may carry active_test=False: ask for active languages explicitly
        lang = code and self.env['res.lang'].search(
            [('code', '=like', code + '_%'), ('active', '=', True)], limit=1)
        return lang.code if lang else self.env.lang or 'en_US'

    def _bot(self):
        return self.env['telegram.bot']

    def _say(self, text, keyboard=None, reply_keyboard=None):
        return self._bot()._send(self.chat_id, text, keyboard=keyboard, reply_keyboard=reply_keyboard)

    # ------------------------------------------------------------------
    # routing
    # ------------------------------------------------------------------
    def _on_text(self, text):
        if text.startswith('/'):
            command = text.split()[0].split('@')[0][1:].lower()
            self._reset_state()
            handler = getattr(self, '_cmd_' + command, None)
            return handler() if handler else self._cmd_help()
        return self._on_free_text(text)

    def _on_callback(self, data, message):
        key, _sep, arg = data.partition(':')
        handler = getattr(self, '_cb_' + key, None) if key.isidentifier() else None
        if handler:
            handler(arg, message)

    def _reset_state(self):
        self.write({'state': 'idle'})

    def _on_free_text(self, text):
        """Text without a leading slash. Base: show the help."""
        self._cmd_help()

    def _on_location(self, location):
        """`location` carries latitude and longitude. Base: nothing to do."""
        self._cmd_help()

    # ------------------------------------------------------------------
    # base commands
    # ------------------------------------------------------------------
    def _cmd_start(self):
        self._say(escape(self._bot()._param('welcome') or _("Hi! Send /help to see what I can do.")))

    def _cmd_help(self):
        lines = ["/%s - %s" % (command, escape(label)) for command, label in self._bot()._commands()]
        self._say("\n".join(lines))

    def _cmd_stop(self):
        self.write({'active': False, 'state': 'idle'})
        self._say(_("Bye. Send /start whenever you want to come back."),
                  reply_keyboard={'remove_keyboard': True})
