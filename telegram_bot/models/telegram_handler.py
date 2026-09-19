# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from html import escape

from odoo import _, models


class TelegramHandler(models.AbstractModel):
    """Conversation logic of a bot kind. Every method receives the chat record.

    A module adds a kind by extending `telegram.bot.kind` with selection_add and
    defining `telegram.handler.<kind>` that inherits this model. Routing:
    `/command` -> `_cmd_<command>(chat)`, button data `key:arg` -> `_cb_<key>(chat, arg,
    message)`, plain text -> `_on_free_text(chat, text)`, shared location ->
    `_on_location(chat, location)`.
    """
    _name = 'telegram.handler'
    _description = "Telegram Conversation Handler"

    def _commands(self):
        """[(command, description)] shown by /help and registered with setMyCommands.

        Build the list from keyword arguments: a tuple opened right after a _() call
        confuses the term extractor.
        """
        return list(dict(start=_("Start"), help=_("Help")).items())

    # ------------------------------------------------------------------
    # routing
    # ------------------------------------------------------------------
    def _on_text(self, chat, text):
        if text.startswith('/'):
            command = text.split()[0].split('@')[0][1:].lower()
            chat._reset_state()
            handler = getattr(self, '_cmd_' + command, None)
            return handler(chat) if handler else self._cmd_help(chat)
        return self._on_free_text(chat, text)

    def _on_callback(self, chat, data, message):
        key, _sep, arg = data.partition(':')
        handler = getattr(self, '_cb_' + key, None) if key.isidentifier() else None
        if handler:
            handler(chat, arg, message)

    def _on_free_text(self, chat, text):
        """Text without a leading slash. Base: show the help."""
        self._cmd_help(chat)

    def _on_location(self, chat, location):
        """`location` carries latitude and longitude. Base: show the help."""
        self._cmd_help(chat)

    # ------------------------------------------------------------------
    # base commands
    # ------------------------------------------------------------------
    def _cmd_start(self, chat):
        chat._say(escape(chat.bot_id.welcome or _("Hi! Send /help to see what I can do.")))

    def _cmd_help(self, chat):
        lines = ["/%s - %s" % (command, escape(label)) for command, label in self._commands()]
        chat._say("\n".join(lines))

    def _cmd_stop(self, chat):
        chat.write({'active': False, 'state': 'idle'})
        chat._say(_("Bye. Send /start whenever you want to come back."),
                  reply_keyboard={'remove_keyboard': True})
