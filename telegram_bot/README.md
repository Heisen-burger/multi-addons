# Telegram Bot

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

Generic Telegram Bot API layer for Odoo: webhook endpoint, chat registry, command and
callback routing, HTML message helper. Other modules add commands and conversation logic
by inheriting `telegram.chat` and `telegram.bot`. No Python dependency beyond `requests`.

## What it does

- **Webhook** `POST /telegram_bot/webhook`, `auth='none'`, checked against the
  `X-Telegram-Bot-Api-Secret-Token` header. Always answers 200 so Telegram never retries;
  handler errors go to the log.
- **`telegram.chat`**: one record per chat (user or group), created on first message,
  archived on `/stop` or when the user blocks the bot, revived by any later message.
  `state` drives multi-step conversations; extensions add values with `selection_add`.
- **Routing**: `/command` calls `_cmd_<command>()`, unknown commands show `/help`;
  inline button data `key:arg` calls `_cb_<key>(arg, message)`; plain text goes to
  `_on_free_text(text)`; a shared location goes to `_on_location(location)`.
- **`telegram.bot`** (abstract): `_call(method, **payload)`, `_send(chat_id, text,
  keyboard=..., reply_keyboard=...)` in HTML mode, `_commands()` for `/help` and
  `setMyCommands`, `action_register_webhook()` that generates the secret when empty and
  registers the webhook on `web.base.url`.

## Configuration

1. Create the bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Settings > Telegram: paste the token, save.
3. Settings > Technical > Telegram > Register Webhook. The notification shows the webhook
   URL and the last error reported by Telegram.

`web.base.url` must be the public HTTPS address of the instance.

## Extending

```python
class TelegramBot(models.AbstractModel):
    _inherit = 'telegram.bot'

    def _commands(self):
        return super()._commands() + [('orders', "My open orders")]


class TelegramChat(models.Model):
    _inherit = 'telegram.chat'

    def _cmd_orders(self):
        self._say("<b>3</b> open orders", keyboard=[[{'text': "Open", 'callback_data': 'order:42'}]])

    def _cb_order(self, arg, message):
        self._say("Order %s" % arg)
```

Tests can reuse `odoo.addons.telegram_bot.tests.common.TelegramCase`: it patches `_call`,
records every API call in `self.calls` and offers `send_text`, `send_location`, `tap`.

## Models

| Model | Purpose |
|---|---|
| `telegram.chat` | chat registry and conversation routing |
| `telegram.bot` | Bot API client, abstract |

## Access rights

`telegram.chat`: read for internal users, full access for administrators. The webhook runs
as superuser after the secret check.

## Changelog

### 19.0.1.0.0

- Initial release.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
