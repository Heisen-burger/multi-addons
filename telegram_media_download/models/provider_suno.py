# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
import re
from html import escape

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

from .media_provider import USER_AGENT

_logger = logging.getLogger(__name__)

UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
STUDIO_API = 'https://studio-api.prod.suno.com/api'
CLIP_API = STUDIO_API + '/clip/%s'
FEED_API = STUDIO_API + '/feed/v2?ids=%s'
VIDEO_URL = 'https://cdn1.suno.ai/%s.mp4'
CLERK_API = 'https://auth.suno.com/v1'
CLERK_QS = '?__clerk_api_version=2025-11-10&_clerk_js_version=5.117.0'
COOKIE_PARAM = 'telegram_media.suno_client_cookie'


class TelegramMediaProviderSuno(models.AbstractModel):
    """Suno.

    Public clips: metadata from the studio API, audio track pulled out of the public mp4.
    Own and private clips: Suno serves them to the account that owns them, so the bot needs
    the `__client` cookie of a logged-in session. The cookie buys a short lived JWT from
    Clerk, and the authenticated clip carries a real `audio_url`.

    The `media_urls` stream is encrypted and the player decrypts it in the browser. The bot
    does not touch it: without a session it simply reports what is missing.
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

    # ------------------------------------------------------------------
    # authenticated access
    # ------------------------------------------------------------------
    @api.model
    def _client_cookie(self):
        return (self.env['ir.config_parameter'].sudo().get_param(COOKIE_PARAM) or '').strip()

    @api.model
    def _session(self):
        """Return (jwt, error). `jwt` is None when the cookie is missing, expired or rejected."""
        cookie = self._client_cookie()
        if not cookie:
            return None, _("no Suno session cookie configured")
        headers = {'Authorization': cookie, 'User-Agent': USER_AGENT}
        try:
            client = requests.get(CLERK_API + '/client' + CLERK_QS, headers=headers, timeout=30)
            client.raise_for_status()
            payload = (client.json() or {}).get('response') or {}
            sid = payload.get('last_active_session_id')
            if not sid:
                return None, _("the cookie carries no active Suno session, log in again and copy it")
            token = requests.post(CLERK_API + '/client/sessions/%s/tokens' % sid + CLERK_QS,
                                  headers=headers, timeout=30)
            token.raise_for_status()
            jwt = (token.json() or {}).get('jwt')
            return (jwt, None) if jwt else (None, _("Suno returned no token for this session"))
        except (requests.RequestException, TypeError, ValueError) as error:
            _logger.warning("Suno session cookie rejected: %s", error)
            return None, str(error)[:200]

    def _authenticated_clip(self, clip_id, jwt):
        """Clip JSON as the logged-in account sees it, from the feed or the clip endpoint."""
        headers = {'Authorization': 'Bearer %s' % jwt, 'User-Agent': USER_AGENT}
        try:
            response = requests.get(FEED_API % clip_id, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            clips = data.get('clips') if isinstance(data, dict) else data
            clip = (clips or [None])[0]
            if clip and clip.get('audio_url'):
                return clip
        except (requests.RequestException, ValueError) as error:
            _logger.info("Suno feed for %s failed: %s", clip_id, error)
        response = requests.get(CLIP_API % clip_id, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    @api.model
    def action_test_session(self):
        """Report whether the configured cookie still opens a Suno session."""
        jwt, error = self._session()
        if not jwt:
            message = _("Suno session unusable: %s") % error
        else:
            try:
                clip = self._authenticated_clip('4d4b9cf4-3af8-4a99-8f48-a9e39b097998', jwt) or {}
                audio = clip.get('audio_url') or ''
                message = _("Token obtained. Test clip audio: %s") % (audio or _("none"))
            except (requests.RequestException, ValueError) as probe_error:
                message = _("Token obtained, but the clip call failed: %s") % str(probe_error)[:200]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Suno session") if jwt else _("Suno session missing"),
                'message': message,
                'type': 'success' if jwt else 'warning',
                'sticky': True,
            },
        }

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------
    def _fetch(self, url):
        clip_id = self._clip_id(url)
        meta = self._http_get(CLIP_API % clip_id, timeout=30).json()
        if meta.get('status') not in (None, 'complete'):
            raise UserError(_("This Suno track is not ready yet (status %s).") % meta.get('status'))

        source = None
        jwt, session_error = self._session()
        if jwt:
            try:
                clip = self._authenticated_clip(clip_id, jwt) or {}
                audio_url = clip.get('audio_url') or ''
                if audio_url and 'forbidden' not in audio_url:
                    source = self._http_get(audio_url, timeout=120,
                                            headers={'Authorization': 'Bearer %s' % jwt,
                                                     'User-Agent': USER_AGENT}).content
                    meta = {**meta, **{k: v for k, v in clip.items() if v}}
                else:
                    session_error = _("the session has no audio for this track")
            except (requests.RequestException, ValueError) as error:
                _logger.warning("Suno authenticated download of %s failed: %s", clip_id, error)
                session_error = str(error)[:200]
        if source is None:
            try:
                if not meta.get('video_url'):
                    raise requests.HTTPError(response=None)
                source = self._http_get(VIDEO_URL % clip_id, timeout=120).content
            except requests.HTTPError:
                raise UserError(_("Suno serves this track only to the account that owns it "
                                  "(%(reason)s). Put the __client cookie of your Suno session in "
                                  "Settings > Telegram Media.", reason=session_error))

        title = meta.get('title') or clip_id
        performer = meta.get('display_name') or "Suno"
        duration = (meta.get('metadata') or {}).get('duration')
        cover = None
        if meta.get('image_url'):
            try:
                cover = self._http_get(meta['image_url'], timeout=30).content
            except Exception as error:  # noqa: BLE001 - cover art is optional
                _logger.info("Suno cover for %s skipped: %s", clip_id, error)
        data = self._to_mp3(source, title=title, performer=performer, cover=cover, source_ext='.bin')
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
