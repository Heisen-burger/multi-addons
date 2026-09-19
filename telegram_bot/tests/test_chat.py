# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from unittest.mock import patch

from odoo.tests import tagged

from .common import TelegramCase


@tagged('post_install', '-at_install')
class TestChat(TelegramCase):
    def test_start_creates_chat_and_answers(self):
        self.env['ir.config_parameter'].sudo().set_param('telegram_bot.welcome', "Welcome <here>")
        self.send_text('/start@my_bot')
        self.assertRecordValues(self.chat(), [{'name': "Mario Rossi", 'username': 'mrossi', 'lang': 'it', 'state': 'idle'}])
        self.assertEqual(self.calls[0][0], 'sendMessage')
        self.assertEqual(self.last_text(), "Welcome &lt;here&gt;")

    def test_unknown_command_and_free_text_show_help(self):
        self.send_text('/whatever')
        self.assertIn("/start", self.last_text())
        self.send_text('hello')
        self.assertIn("/help", self.last_text())

    def test_callback_routes_to_cb_method(self):
        seen = []
        with patch.object(type(self.Chat), '_cb_demo', create=True, new=lambda self, arg, message: seen.append(arg)):
            self.tap('demo:42')
            self.tap('missing:1')
            self.tap('not valid:1')
        self.assertEqual(seen, ['42'])
        self.assertEqual(self.sent('answerCallbackQuery')[0]['callback_query_id'], 'cb1')

    def test_stop_archives_and_next_message_revives(self):
        self.send_text('/stop')
        self.assertFalse(self.chat().active)
        self.assertEqual(self.sent()[-1]['reply_markup'], {'remove_keyboard': True})
        self.send_text('/start')
        self.assertTrue(self.chat().active)

    def test_blocked_bot_archives_chat(self):
        self.send_text('/start')

        class Response:
            @staticmethod
            def json():
                return {'ok': False, 'error_code': 403, 'description': "Forbidden: bot was blocked by the user"}

        with patch('odoo.addons.telegram_bot.models.telegram_bot.requests.post', return_value=Response()):
            self.real_call(self.env['telegram.bot'], 'sendMessage', chat_id=4242, text="hi")
        self.assertFalse(self.chat().active)

    def test_handle_update_swallows_errors(self):
        with patch.object(type(self.Chat), '_dispatch', side_effect=ValueError("boom")):
            self.Chat._handle_update({'update_id': 9})

    def test_register_webhook_sets_secret_and_commands(self):
        self.env['ir.config_parameter'].sudo().set_param('telegram_bot.webhook_secret', False)
        action = self.env['telegram.bot'].action_register_webhook()
        secret = self.env['ir.config_parameter'].sudo().get_param('telegram_bot.webhook_secret')
        self.assertTrue(secret)
        hook = self.sent('setWebhook')[0]
        self.assertEqual(hook['secret_token'], secret)
        self.assertTrue(hook['url'].endswith('/telegram_bot/webhook'))
        self.assertEqual([c['command'] for c in self.sent('setMyCommands')[0]['commands']][:2], ['start', 'help'])
        self.assertEqual(action['params']['type'], 'success')
