# Telegram Bot

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

Generic Telegram Bot API layer for Odoo: any number of bots, one webhook per bot, chat
registry, access code, command and callback routing, HTML messages and file uploads. Other
modules add a bot kind by inheriting two models. No Python dependency beyond `requests`.

## What it does

- **`telegram.bot`**: one record per bot with token, kind, webhook secret, access code and
  welcome text. *Register Webhook* on the form fills the username (`getMe`), generates the
  secret when empty, calls `setWebhook` on `<web.base.url>/telegram_bot/webhook/<id>` and
  `setMyCommands` with the handler's command list.
- **Webhook** `POST /telegram_bot/webhook/<bot_id>`, `auth='none'`, checked against the
  `X-Telegram-Bot-Api-Secret-Token` header of that bot. Always answers 200 so Telegram
  never retries; handler errors go to the log.
- **`telegram.chat`**: one record per (bot, chat), created on first message, archived on
  `/stop` or when the user blocks the bot, revived by any later message. `state` drives
  multi-step conversations; extensions add values with `selection_add`.
- **`telegram.handler`** (abstract): the conversation of a bot kind. `/command` calls
  `_cmd_<command>(chat)`, unknown commands show `/help`; inline button data `key:arg` calls
  `_cb_<key>(chat, arg, message)`; plain text goes to `_on_free_text(chat, text)`; a shared
  location goes to `_on_location(chat, location)`.
- **Client** on the bot record: `_call(method, files=None, **payload)`, `_send(chat_id,
  text, keyboard=..., reply_keyboard=...)` in HTML mode, `_send_file(chat_id, kind, data,
  filename, caption=..., **meta)` for audio, video, voice, photo and document uploads
  (50 MB cap on Telegram's side), `_send_audio(...)` shortcut.

## Access code

Set it on the bot. A new chat gets "This bot is private" until it sends `/start <code>`;
the link `https://t.me/<bot>?start=<code>` does it in one tap. Admitted chats keep the
`authorized` flag, so changing the code later does not lock them out; untick the flag on a
chat record to ban it. Empty code: every chat is admitted on its first message.

## Configuration

1. Create the bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Settings > Technical > Telegram > Bots: new record, paste the token, pick the kind, save.
3. *Register Webhook*. The notification shows the webhook URL and the last error reported by
   Telegram.

`web.base.url` must be the public HTTPS address of the instance. Set
`web.base.url.freeze = True` when Odoo sits behind a proxy, otherwise a login rewrites it
with the internal hostname.

## Adding a bot kind

```python
class TelegramBot(models.Model):
    _inherit = 'telegram.bot'
    kind = fields.Selection(selection_add=[('orders', "Orders")], ondelete={'orders': 'set default'})


class TelegramHandlerOrders(models.AbstractModel):
    _name = 'telegram.handler.orders'
    _inherit = 'telegram.handler'

    def _commands(self):
        own = dict(orders=_("My open orders"))
        return super()._commands() + list(own.items())

    def _cmd_orders(self, chat):
        chat._say("<b>3</b> open orders", keyboard=[[{'text': "Open", 'callback_data': 'order:42'}]])

    def _cb_order(self, chat, arg, message):
        chat._say("Order %s" % arg)
```

Build command lists from keyword arguments and keep `_()` calls out of tuples and
conditionals: Odoo's term extractor treats a parenthesis right after `_()` as another
translation call.

Tests reuse `odoo.addons.telegram_bot.tests.common.TelegramCase`: it creates `cls.bot`,
patches `_call`, records every API call in `self.calls` and offers `send_text`,
`send_location`, `tap`, `sent`, `last_text`, `last_buttons`.

## Models

| Model | Purpose |
|---|---|
| `telegram.bot` | bot record, Bot API client, webhook registration and dispatch |
| `telegram.chat` | chat registry per bot, access check, `_say` |
| `telegram.handler` | conversation of a kind, abstract |

## Access rights

`telegram.bot` and `telegram.chat`: read for internal users, full access for
administrators. Token and secret are visible to administrators only. The webhook runs as
superuser after the secret check.

## Upgrading from 19.0.1.x

The migration turns the settings-based bot into a `telegram.bot` record and attaches every
chat to it. The webhook URL now carries the bot id: open the bot and press *Register
Webhook* once.

## Changelog

### 19.0.2.0.0

- Several bots: `telegram.bot` record with kind, token, secret, access code and welcome;
  webhook per bot; conversation moved to `telegram.handler.<kind>`.
- `_send_file` for audio, video, voice, photo and document uploads.

### 19.0.1.1.0

- Access code: new chats must send `/start <code>` when one is configured.

### 19.0.1.0.1

- Test helper `last_buttons` skips url buttons.

### 19.0.1.0.0

- Initial release.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
