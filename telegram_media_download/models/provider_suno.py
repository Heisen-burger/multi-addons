# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
import re
from html import escape

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
CLIP_API = 'https://studio-api.prod.suno.com/api/clip/%s'
VIDEO_URL = 'https://cdn1.suno.ai/%s.mp4'


class TelegramMediaProviderSuno(models.AbstractModel):
    """Suno: public clip metadata from the studio API, audio track pulled out of the public mp4.

    The direct mp3 and the m4a in `media_urls` are locked (403 / encrypted stream), the
    video on cdn1 is not, so the audio comes from there.
    """
    _name = 'telegram.media.provider.suno'
    _inherit = 'telegram.media.provider'
    _description = "Telegram Media Provider: Suno"

    _provider_name = "Suno"
    _url_pattern = re.compile(r'https?://(?:www\.)?(?:suno\.com|app\.suno\.ai)/(?:song|s)/([A-Za-z0-9-]+)', re.I)

    def _clip_id(self, url):
        match = self._url_pattern.search(url)
        key = match.group(1)
        if UUID_RE.fullmatch(key):
            return key.lower()
        # short link suno.com/s/<code>: a 307 to /song/<uuid>?sh=<code>
        response = self._http_get(url, allow_redirects=False, timeout=30)
        found = UUID_RE.search(response.headers.get('Location', ''))
        if not found:
            raise UserError(_("Could not resolve this Suno link."))
        return found.group(0).lower()

    def _fetch(self, url):
        clip_id = self._clip_id(url)
        meta = self._http_get(CLIP_API % clip_id, timeout=30).json()
        if meta.get('status') not in (None, 'complete'):
            raise UserError(_("This Suno track is not ready yet (status %s).") % meta.get('status'))
        title = meta.get('title') or clip_id
        performer = meta.get('display_name') or "Suno"
        duration = (meta.get('metadata') or {}).get('duration')
        video = self._http_get(VIDEO_URL % clip_id, timeout=120).content
        cover = None
        if meta.get('image_url'):
            try:
                cover = self._http_get(meta['image_url'], timeout=30).content
            except Exception as error:  # noqa: BLE001 - cover art is optional
                _logger.info("Suno cover for %s skipped: %s", clip_id, error)
        data = self._to_mp3(video, title=title, performer=performer, cover=cover)
        tags = (meta.get('metadata') or {}).get('tags')
        caption = "🎵 <b>%s</b>\n👤 %s" % (escape(title), escape(performer))
        if tags:
            caption += "\n🏷 %s" % escape(tags[:200])
        return {
            'kind': 'audio',
            'title': title,
            'performer': performer,
            'duration': duration,
            'filename': self._safe_filename(title),
            'data': data,
            'caption': caption,
        }
