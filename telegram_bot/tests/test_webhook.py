# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.telegram_bot.models.telegram_bot import TelegramBot

UPDATE = {'update_id': 7, 'message': {'message_id': 1, 'text': '/start',
                                      'chat': {'id': 777, 'type': 'private', 'first_name': "Anna"},
                                      'from': {'id': 777, 'language_code': 'it'}}}


@tagged('post_install', '-at_install')
class TestWebhook(HttpCase):
    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('telegram_bot.webhook_secret', 'hook-secret')
        patcher = patch.object(TelegramBot, '_call', autospec=True, return_value={'ok': True})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, secret):
        headers = {'Content-Type': 'application/json'}
        if secret:
            headers['X-Telegram-Bot-Api-Secret-Token'] = secret
        return self.url_open('/telegram_bot/webhook', data=json.dumps(UPDATE), headers=headers)

    def test_wrong_secret_is_forbidden(self):
        self.assertEqual(self._post('nope').status_code, 403)
        self.assertEqual(self._post(None).status_code, 403)
        self.assertFalse(self.env['telegram.chat'].search([('chat_id', '=', 777)]))

    def test_valid_secret_creates_chat(self):
        response = self._post('hook-secret')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})
        self.assertEqual(self.env['telegram.chat'].search([('chat_id', '=', 777)]).name, "Anna")
