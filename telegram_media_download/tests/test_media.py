# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import shutil
import subprocess
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.telegram_bot.tests.common import TelegramCase
from odoo.addons.telegram_media_download.models import telegram_handler
from odoo.addons.telegram_media_download.models.provider_suno import TelegramMediaProviderSuno

SONG = 'https://suno.com/song/4d4b9cf4-3af8-4a99-8f48-a9e39b097998'
TRACK = {'title': "My Song", 'performer': "Band", 'duration': 240.4, 'filename': 'My Song.mp3',
         'data': b'ID3' + b'\0' * 100, 'caption': "<b>My Song</b>"}


@tagged('post_install', '-at_install')
class TestMedia(TelegramCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot.kind = 'media'
        cls.Log = cls.env['telegram.media.download']

    def logs(self):
        return self.Log.search([('chat_id.chat_id', '=', 4242)])

    def test_start_lists_sites(self):
        self.send_text('/start')
        self.assertIn("Suno", self.last_text())
        self.send_text('/siti')
        self.assertEqual(self.last_text(), "Suno")

    def test_link_is_downloaded_and_sent_as_audio(self):
        with patch.object(TelegramMediaProviderSuno, '_fetch', autospec=True, return_value=dict(TRACK)) as fetch:
            self.send_text("ascolta %s !" % SONG)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1], SONG)
        audio = self.sent('sendAudio')[0]
        self.assertEqual(audio['files']['audio'], ('My Song.mp3', TRACK['data']))
        self.assertEqual((audio['title'], audio['performer'], audio['duration']), ("My Song", "Band", 240))
        self.assertRecordValues(self.logs(), [{'state': 'done', 'provider': "Suno", 'title': "My Song",
                                               'size': len(TRACK['data']), 'url': SONG}])

    def test_video_track_goes_through_send_video(self):
        clip = dict(TRACK, kind='video', filename='clip.mp4', width=640, height=360)
        clip.pop('title')
        clip.pop('performer')
        with patch.object(TelegramMediaProviderSuno, '_fetch', autospec=True, return_value=clip):
            self.send_text(SONG)
        video = self.sent('sendVideo')[0]
        self.assertEqual(video['files']['video'][0], 'clip.mp4')
        self.assertEqual((video['width'], video['height'], video['duration']), (640, 360, 240))
        self.assertFalse(self.sent('sendAudio'))
        self.assertEqual(self.logs().state, 'done')

    def test_unsupported_link_and_no_link(self):
        self.send_text("https://example.com/track/1")
        self.assertIn("Suno", self.last_text())
        self.assertEqual(self.logs().state, 'unsupported')
        self.send_text("ciao")
        self.assertIn("link", self.last_text())
        self.assertFalse(self.sent('sendAudio'))

    def test_provider_error_is_reported(self):
        with patch.object(TelegramMediaProviderSuno, '_fetch', autospec=True, side_effect=UserError("nope")):
            self.send_text(SONG)
        self.assertIn("nope", self.last_text())
        self.assertRecordValues(self.logs(), [{'state': 'error', 'error': "nope"}])

    def test_too_big_is_refused(self):
        with patch.object(telegram_handler, 'MAX_BYTES', 10), \
                patch.object(TelegramMediaProviderSuno, '_fetch', autospec=True, return_value=dict(TRACK)):
            self.send_text(SONG)
        self.assertEqual(self.logs().state, 'too_big')
        self.assertFalse(self.sent('sendAudio'))

    def test_suno_clip_id_from_song_and_short_link(self):
        suno = self.env['telegram.media.provider.suno']
        self.assertEqual(suno._clip_id(SONG), '4d4b9cf4-3af8-4a99-8f48-a9e39b097998')
        self.assertTrue(suno._matches('https://app.suno.ai/song/4d4b9cf4-3af8-4a99-8f48-a9e39b097998'))
        self.assertFalse(suno._matches('https://suno.com/playlist/abc'))

        class Redirect:
            headers = {'Location': '/song/20f569e1-fb1b-4b4e-af8e-8518ffb5837a?sh=kuuNnXWLBeiaN1wU'}

        with patch.object(type(suno), '_http_get', return_value=Redirect()):
            self.assertEqual(suno._clip_id('https://suno.com/s/kuuNnXWLBeiaN1wU'), '20f569e1-fb1b-4b4e-af8e-8518ffb5837a')

    def test_to_mp3_with_ffmpeg(self):
        if not shutil.which('ffmpeg'):
            self.skipTest("ffmpeg not installed")
        wav = subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                              '-f', 'wav', '-'], capture_output=True, check=True).stdout
        mp3 = self.env['telegram.media.provider']._to_mp3(wav, title="Tone", performer="Test", source_ext='.wav')
        self.assertTrue(mp3.startswith(b'ID3'))
        self.assertIn(b'Tone', mp3[:2000])
