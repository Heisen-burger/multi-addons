# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import _, api, fields, models


class TelegramChat(models.Model):
    """One record per (bot, Telegram chat). Conversation logic lives in the bot's handler."""
    _name = 'telegram.chat'
    _description = "Telegram Chat"
    _order = 'name, id'

    bot_id = fields.Many2one('telegram.bot', required=True, index=True, ondelete='cascade')
    chat_id = fields.Integer("Telegram Chat ID", required=True, index=True)
    name = fields.Char(required=True)
    username = fields.Char()
    lang = fields.Char("Telegram Language")
    state = fields.Selection([('idle', "Idle")], default='idle', required=True,
                             help="Conversation state. Extensions add values with selection_add.")
    active = fields.Boolean(default=True)
    authorized = fields.Boolean(help="The chat sent the access code, or none was required when it first wrote.")

    _bot_chat_unique = models.Constraint(
        'unique (bot_id, chat_id)',
        "This Telegram chat is already registered for this bot.",
    )

    @api.model
    def _get_chat(self, bot, tg_chat, tg_from):
        """Find or create the chat record; any message revives an archived chat."""
        name = tg_chat.get('title') or ' '.join(
            part for part in (tg_chat.get('first_name'), tg_chat.get('last_name')) if part
        ) or str(tg_chat['id'])
        vals = {'bot_id': bot.id, 'chat_id': tg_chat['id'], 'name': name,
                'username': tg_chat.get('username') or False,
                'lang': (tg_from or {}).get('language_code') or False, 'active': True}
        chat = self.with_context(active_test=False).search(
            [('bot_id', '=', bot.id), ('chat_id', '=', tg_chat['id'])], limit=1)
        if chat:
            changed = {key: value for key, value in vals.items() if chat[key] != value}
            if changed:
                chat.write(changed)
        else:
            chat = self.create(vals)
        return chat.with_context(lang=chat._odoo_lang())

    def _check_bot_access(self, text=''):
        """True when the chat may talk to the bot.

        Never name this _check_access: it shadows the ORM method and every view of the
        model then fails with "'bool' object is not subscriptable".

        With an access code on the bot, a chat is admitted once it sends '/start <code>'
        (also the payload of a t.me/<bot>?start=<code> link). Without a code every chat is
        admitted on its first message.
        """
        if self.authorized:
            return True
        code = (self.bot_id.access_code or '').strip()
        parts = text.split(maxsplit=1)
        if not code or (parts and parts[0].split('@')[0] == '/start' and len(parts) > 1 and parts[1].strip() == code):
            self.write({'authorized': True})
            return True
        self._say(_("This bot is private. Send /start followed by the access code."))
        return False

    def _odoo_lang(self):
        self.ensure_one()
        code = (self.lang or '').split('-')[0]
        # the record may carry active_test=False: ask for active languages explicitly
        lang = code and self.env['res.lang'].search(
            [('code', '=like', code + '_%'), ('active', '=', True)], limit=1)
        return lang.code if lang else self.env.lang or 'en_US'

    def _say(self, text, keyboard=None, reply_keyboard=None):
        self.ensure_one()
        return self.bot_id._send(self.chat_id, text, keyboard=keyboard, reply_keyboard=reply_keyboard)

    def _reset_state(self):
        self.write({'state': 'idle'})
