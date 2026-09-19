# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.telegram_bot.models.telegram_bot import TelegramBot

CHAT = {'id': 4242, 'type': 'private', 'first_name': "Mario", 'last_name': "Rossi", 'username': 'mrossi'}
FROM = {'id': 4242, 'language_code': 'it'}


class TelegramCase(TransactionCase):
    """Creates a bot, patches the Bot API client and records every call.

    Bot extensions reuse it: set `cls.bot.kind` in their setUpClass.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.real_call = staticmethod(TelegramBot._call)  # captured before setUp patches it
        cls.bot = cls.env['telegram.bot'].create({
            'name': "Test bot", 'token': 'test-token', 'webhook_secret': 'test-secret',
        })
        cls.Chat = cls.env['telegram.chat']

    def setUp(self):
        super().setUp()
        self.calls = []

        def fake_call(_bot, method, files=None, **payload):
            self.calls.append((method, dict(payload, files=files) if files else payload))
            return {'ok': True, 'result': {}}

        patcher = patch.object(TelegramBot, '_call', autospec=True, side_effect=fake_call)
        patcher.start()
        self.addCleanup(patcher.stop)

    # helpers -------------------------------------------------------------
    def send_text(self, text):
        self.bot._dispatch({'update_id': 1, 'message': {'message_id': 10, 'chat': CHAT, 'from': FROM, 'text': text}})

    def send_location(self, lat, lng):
        self.bot._dispatch({'update_id': 2, 'message': {
            'message_id': 11, 'chat': CHAT, 'from': FROM, 'location': {'latitude': lat, 'longitude': lng}}})

    def tap(self, data):
        self.bot._dispatch({'update_id': 3, 'callback_query': {
            'id': 'cb1', 'from': FROM, 'data': data, 'message': {'message_id': 12, 'chat': CHAT}}})

    def chat(self):
        return self.Chat.with_context(active_test=False).search(
            [('bot_id', '=', self.bot.id), ('chat_id', '=', CHAT['id'])])

    def sent(self, method='sendMessage'):
        return [payload for name, payload in self.calls if name == method]

    def last_text(self):
        return self.sent()[-1]['text']

    def last_buttons(self):
        rows = self.sent()[-1].get('reply_markup', {}).get('inline_keyboard', [])
        return [button['callback_data'] for row in rows for button in row if 'callback_data' in button]
