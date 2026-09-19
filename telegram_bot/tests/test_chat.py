# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.telegram_bot.models.telegram_handler import TelegramHandler

from .common import TelegramCase


@tagged('post_install', '-at_install')
class TestChat(TelegramCase):
    def test_start_creates_chat_and_answers(self):
        self.bot.welcome = "Welcome <here>"
        self.send_text('/start@my_bot')
        self.assertRecordValues(self.chat(), [{'name': "Mario Rossi", 'username': 'mrossi', 'lang': 'it',
                                               'state': 'idle', 'bot_id': self.bot.id}])
        self.assertEqual(self.calls[0][0], 'sendMessage')
        self.assertEqual(self.last_text(), "Welcome &lt;here&gt;")

    def test_unknown_command_and_free_text_show_help(self):
        self.send_text('/whatever')
        self.assertIn("/start", self.last_text())
        self.send_text('hello')
        self.assertIn("/help", self.last_text())

    def test_callback_routes_to_cb_method(self):
        seen = []
        with patch.object(TelegramHandler, '_cb_demo', create=True,
                          new=lambda self, chat, arg, message: seen.append((chat.chat_id, arg))):
            self.tap('demo:42')
            self.tap('missing:1')
            self.tap('not valid:1')
        self.assertEqual(seen, [(4242, '42')])
        self.assertEqual(self.sent('answerCallbackQuery')[0]['callback_query_id'], 'cb1')

    def test_stop_archives_and_next_message_revives(self):
        self.send_text('/stop')
        self.assertFalse(self.chat().active)
        self.assertEqual(self.sent()[-1]['reply_markup'], {'remove_keyboard': True})
        self.send_text('/start')
        self.assertTrue(self.chat().active)

    def test_access_code_gates_new_chats(self):
        self.bot.access_code = 'sesame'
        self.send_text('/start')
        self.assertFalse(self.chat().authorized)
        self.assertIn("private", self.last_text())
        self.send_text('/start wrong')
        self.assertFalse(self.chat().authorized)
        self.tap('demo:1')
        self.assertIn("private", self.last_text())
        self.calls.clear()
        self.send_text('/start sesame')
        self.assertTrue(self.chat().authorized)
        self.assertNotIn("private", self.last_text())
        self.send_text('/help')
        self.assertIn("/start", self.last_text())

    def test_no_access_code_admits_everyone(self):
        self.send_text('/help')
        self.assertTrue(self.chat().authorized)

    def test_same_telegram_chat_on_two_bots_are_two_records(self):
        other = self.env['telegram.bot'].create({'name': "Other", 'token': 'other-token'})
        self.send_text('/help')
        other._dispatch({'update_id': 5, 'message': {'message_id': 1, 'chat': {'id': 4242, 'type': 'private',
                                                                                 'first_name': "Mario"}, 'text': '/help'}})
        chats = self.Chat.search([('chat_id', '=', 4242)])
        self.assertEqual(set(chats.mapped('bot_id').ids), {self.bot.id, other.id})

    def test_blocked_bot_archives_chat(self):
        self.send_text('/start')

        class Response:
            @staticmethod
            def json():
                return {'ok': False, 'error_code': 403, 'description': "Forbidden: bot was blocked by the user"}

        with patch('odoo.addons.telegram_bot.models.telegram_bot.requests.post', return_value=Response()):
            self.real_call(self.bot, 'sendMessage', chat_id=4242, text="hi")
        self.assertFalse(self.chat().active)

    def test_send_file_uploads_multipart(self):
        self.bot._send_audio(4242, b"ID3...", "song.mp3", title="Song", performer="Band", duration=12.7)
        payload = self.sent('sendAudio')[0]
        self.assertEqual(payload['files']['audio'], ("song.mp3", b"ID3..."))
        self.assertEqual((payload['title'], payload['performer'], payload['duration']), ("Song", "Band", 12))
        self.bot._send_file(4242, 'video', b"\0\0ftyp", "clip.mp4", caption="<b>Clip</b>", duration=3, width=640,
                            height=360, title="ignored for video")
        payload = self.sent('sendVideo')[0]
        self.assertEqual(payload['files']['video'], ("clip.mp4", b"\0\0ftyp"))
        self.assertEqual((payload['width'], payload['height'], payload['caption']), (640, 360, "<b>Clip</b>"))
        self.assertNotIn('title', payload)

    def test_handle_update_swallows_errors(self):
        with patch.object(type(self.bot), '_dispatch', side_effect=ValueError("boom")):
            self.bot._handle_update({'update_id': 9})

    def test_register_webhook_sets_secret_and_commands(self):
        self.bot.webhook_secret = False
        action = self.bot.action_register_webhook()
        self.assertTrue(self.bot.webhook_secret)
        hook = self.sent('setWebhook')[0]
        self.assertEqual(hook['secret_token'], self.bot.webhook_secret)
        self.assertTrue(hook['url'].endswith('/telegram_bot/webhook/%s' % self.bot.id))
        self.assertEqual([c['command'] for c in self.sent('setMyCommands')[0]['commands']][:2], ['start', 'help'])
        self.assertEqual(action['params']['type'], 'success')
