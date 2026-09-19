# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
import re
from html import escape

from odoo import _, models

_logger = logging.getLogger(__name__)

URL_RE = re.compile(r'https?://[^\s<>"]+')
MAX_BYTES = 49 * 1024 * 1024  # Telegram bots upload 50 MB at most
MAX_LINKS_PER_MESSAGE = 3


class TelegramHandlerMedia(models.AbstractModel):
    """Conversation of the media download bot (telegram.bot.kind = 'media')."""
    _name = 'telegram.handler.media'
    _inherit = 'telegram.handler'
    _description = "Telegram Handler: Media Download"

    def _commands(self):
        own = dict(siti=_("Supported sites"))
        return super()._commands() + list(own.items())

    def _providers(self):
        return self.env['telegram.media.provider']._all()

    def _sites_line(self):
        return ", ".join(p._provider_name for p in self._providers())

    def _cmd_start(self, chat):
        chat._say(_("Send me a link and I reply with the file (MP3 for music, video where the site "
                    "offers one).\nSupported sites: %s") % escape(self._sites_line()))

    def _cmd_siti(self, chat):
        chat._say(escape(self._sites_line()))

    def _on_free_text(self, chat, text):
        urls = URL_RE.findall(text)
        if not urls:
            return chat._say(_("Send me a link to a track. Supported sites: %s") % escape(self._sites_line()))
        for url in urls[:MAX_LINKS_PER_MESSAGE]:
            self._download(chat, url.rstrip('.,;)'))

    def _download(self, chat, url):
        Log = self.env['telegram.media.download']
        provider = self.env['telegram.media.provider']._for_url(url)
        log = Log.create({'chat_id': chat.id, 'url': url, 'provider': provider and provider._provider_name})
        if provider is None:
            log.state = 'unsupported'
            return chat._say(_("I cannot download from this link. Supported sites: %s") % escape(self._sites_line()))
        chat._say(_("⏳ Downloading from %s, a few seconds…") % escape(provider._provider_name))
        try:
            track = provider._fetch(url)
        except Exception as error:  # noqa: BLE001 - report to the user, keep the webhook alive
            _logger.warning("Media download %s failed: %s", url, error)
            log.write({'state': 'error', 'error': str(error)[:1000]})
            return chat._say(_("Download failed: %s") % escape(str(error)[:300]))
        size = len(track['data'])
        log.write({'title': track.get('title'), 'performer': track.get('performer'), 'size': size})
        if size > MAX_BYTES:
            log.state = 'too_big'
            return chat._say(_("The file weighs %.1f MB, above the 50 MB Telegram allows a bot.") % (size / 1048576))
        meta = {key: value for key, value in track.items()
                if key not in ('data', 'filename', 'kind', 'caption')}
        result = chat.bot_id._send_file(chat.chat_id, track.get('kind') or 'audio', track['data'],
                                        track['filename'], caption=track.get('caption'), **meta)
        if result.get('ok'):
            log.state = 'done'
        else:
            log.write({'state': 'error', 'error': result.get('description') or "sendAudio failed"})
            chat._say(_("Telegram refused the file: %s") % escape(result.get('description') or "?"))
