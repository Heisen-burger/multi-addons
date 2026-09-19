# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import os
import re
import subprocess
import tempfile

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) OdooTelegramBot/1.0'
FFMPEG_TIMEOUT = 300


class TelegramMediaProvider(models.AbstractModel):
    """One site = one model `telegram.media.provider.<site>` inheriting this one.

    A provider sets `_provider_name` and `_url_pattern` (compiled regex) and implements
    `_fetch(url)` returning a dict with `data` (bytes), `filename`, `kind` (audio, video,
    voice, photo or document; audio when missing), `caption` (HTML) and the optional
    fields of the matching Bot API method: `title`, `performer`, `duration` for audio,
    `duration`, `width`, `height` for video.
    """
    _name = 'telegram.media.provider'
    _description = "Telegram Media Provider"

    _provider_name = "?"
    _url_pattern = None

    @api.model
    def _all(self):
        return [self.env[name] for name in sorted(self.env.registry)
                if name.startswith('telegram.media.provider.')]

    @api.model
    def _for_url(self, url):
        for provider in self._all():
            if provider._matches(url):
                return provider
        return None

    def _matches(self, url):
        return bool(self._url_pattern and self._url_pattern.search(url))

    def _fetch(self, url):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # helpers shared by providers
    # ------------------------------------------------------------------
    @api.model
    def _http_get(self, url, **kwargs):
        kwargs.setdefault('timeout', 60)
        kwargs.setdefault('headers', {'User-Agent': USER_AGENT})
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        return response

    @staticmethod
    def _safe_filename(title, ext='.mp3'):
        name = re.sub(r'[^\w\s-]', '', title or '', flags=re.U).strip() or 'track'
        return re.sub(r'\s+', ' ', name)[:80] + ext

    @api.model
    def _to_mp3(self, source, title=None, performer=None, cover=None, source_ext='.mp4'):
        """Extract the audio track of `source` (bytes) into an MP3 with ID3 tags and cover art."""
        with tempfile.TemporaryDirectory(prefix='tg_media_') as tmp:
            src = os.path.join(tmp, 'source' + source_ext)
            out = os.path.join(tmp, 'track.mp3')
            with open(src, 'wb') as handle:
                handle.write(source)
            command = ['ffmpeg', '-y', '-loglevel', 'error', '-i', src]
            if cover:
                cover_path = os.path.join(tmp, 'cover.jpg')
                with open(cover_path, 'wb') as handle:
                    handle.write(cover)
                command += ['-i', cover_path, '-map', '0:a:0', '-map', '1:v:0', '-c:v', 'copy',
                            '-metadata:s:v', 'title=Album cover', '-metadata:s:v', 'comment=Cover (front)']
            else:
                command += ['-map', '0:a:0']
            command += ['-c:a', 'libmp3lame', '-q:a', '2', '-id3v2_version', '3']
            if title:
                command += ['-metadata', 'title=%s' % title]
            if performer:
                command += ['-metadata', 'artist=%s' % performer]
            command.append(out)
            try:
                result = subprocess.run(command, capture_output=True, timeout=FFMPEG_TIMEOUT, check=False)
            except FileNotFoundError:
                raise UserError(_("ffmpeg is not installed on the server."))
            except subprocess.TimeoutExpired:
                raise UserError(_("Audio conversion timed out."))
            if result.returncode != 0:
                raise UserError(_("Audio conversion failed: %s") % result.stderr.decode(errors='replace')[-400:])
            with open(out, 'rb') as handle:
                return handle.read()
