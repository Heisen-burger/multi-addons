# Telegram Media Download Bot

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

A Telegram bot kind on top of `telegram_bot`: send a link, get the file back. One provider
per site; Suno ships with the module. Providers decide what they return: an MP3 today, a
video or a document tomorrow, the handler sends whatever comes back with the matching Bot
API method.

## How it works

1. The chat sends a message with one or more links (three at most per message).
2. `telegram.media.provider._for_url` picks the first provider whose regex matches.
3. The bot answers "⏳ Downloading", the provider fetches the track, the handler sends it
   with `sendAudio`, `sendVideo`, `sendVoice`, `sendPhoto` or `sendDocument` depending on
   the `kind` the provider returned, and logs the outcome in `telegram.media.download`.
4. Unsupported link, provider error or a file above 49 MB: a short message and a log row.

## Suno

| Step | Source |
|---|---|
| `suno.com/song/<uuid>`, `app.suno.ai/song/<uuid>` | uuid from the URL |
| `suno.com/s/<code>` | 307 redirect to `/song/<uuid>` |
| title, artist, duration, cover, tags | `GET https://studio-api.prod.suno.com/api/clip/<uuid>` (public clips, no auth) |
| audio | `https://cdn1.suno.ai/<uuid>.mp4`, audio track re-encoded to MP3 (`ffmpeg`, `libmp3lame -q:a 2`) with ID3 title, artist and cover |

The direct mp3 (`cdn1.suno.ai/<uuid>.mp3`) and the `media_urls` m4a answer 403 or arrive
encrypted, hence the video route. Verified on 2026-09-19.

### Own and private tracks

Private tracks and tracks made with recent models have no public video, and their
`media_urls` stream is encrypted for the web player, so an anonymous download cannot work.
Suno serves those files to the account that owns them, so give the bot a logged-in session:
Settings > Telegram Media > Suno > Session Cookie, paste the value of the `__client` cookie
of suno.com (browser dev tools > Application/Storage > Cookies > `https://suno.com` >
`__client`, a long `eyJ...` string). With it the provider asks Clerk (`auth.suno.com`) for a
short-lived JWT, reads the clip through `GET /api/feed/v2?ids=<uuid>` (falling back to
`/api/clip/<uuid>` with the same token) and downloads its real `audio_url`; the file still
goes through `ffmpeg` for MP3, ID3 tags and cover.

Settings > Technical > Telegram > Test Suno Session says whether the cookie still opens a
session, without going through Telegram. The bot's own error message names the reason too:
missing cookie, expired session, or a track the session cannot read.

The cookie is a credential of the Suno account: keep it to administrators (the field is a
password field) and log out of Suno to revoke it.

## Adding a site

One file in `models/`, registered in `models/__init__.py`:

```python
class TelegramMediaProviderExample(models.AbstractModel):
    _name = 'telegram.media.provider.example'
    _inherit = 'telegram.media.provider'
    _provider_name = "Example"
    _url_pattern = re.compile(r'https?://(?:www\.)?example\.com/track/(\d+)')

    def _fetch(self, url):
        page = self._http_get(url).json()
        video = self._http_get(page['video']).content
        return {
            'kind': 'video',                 # audio (default), video, voice, photo, document
            'data': video,
            'filename': self._safe_filename(page['title'], '.mp4'),
            'caption': "<b>%s</b>" % escape(page['title']),
            'duration': page['seconds'], 'width': 1280, 'height': 720,
        }
```

Helpers on the abstract provider: `_http_get(url, **requests_kwargs)` with a browser
user agent and `raise_for_status`, `_safe_filename(title, ext)`, `_to_mp3(source_bytes,
title=, performer=, cover=, source_ext=)` which runs `ffmpeg` in a temporary directory.

## Requirements

`ffmpeg` on the server (`external_dependencies['bin']`). On the Docker image:
`apt-get install -y ffmpeg`.

## Configuration

Settings > Technical > Telegram > Bots: new bot, kind *Media download*, token from
@BotFather, access code if the bot must stay private, *Register Webhook*.

## Menus

Settings > Technical > Telegram > Media Downloads: every link received with provider,
title, size, state and error.

## Changelog

### 19.0.1.2.0

- Suno: clip endpoint as a fallback when the feed returns no audio, error messages naming
  the reason, and a Test Suno Session entry under Settings > Technical > Telegram.

### 19.0.1.1.0

- Suno: own and private tracks through the `__client` session cookie (Settings > Telegram
  Media); clear message when a track has no public video and no cookie is set.

### 19.0.1.0.0

- Initial release: media bot kind, provider registry, Suno provider, download log.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
