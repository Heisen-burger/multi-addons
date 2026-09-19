# Fuel Price Telegram Bot

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

Telegram bot on top of `telegram_bot` and `fuel_price_observatory`: fuel prices around a
shared location, station search by town, subscriptions per fuel with price thresholds,
alerts on every change the observatory sync detects.

## Bot commands

| Command | Effect |
|---|---|
| `/start` | welcome and a "Send my location" button |
| location | first time: pick a fuel and self/served; then one card per nearest station, cheapest first, with distance, time of the last communication, Navigate and Station buttons |
| town or station name | up to 10 matching stations |
| `/vicini` | repeat the search on the last location |
| `/carburante` | change the fuel (or "All fuels") |
| `/lista` | subscriptions with buttons: thresholds, remove, open station |
| `/prezzi` | current prices of the subscriptions, cheapest first |
| `/soglia` | set thresholds on a subscription |
| `/stop` | remove every subscription |
| `/aiuto` | command list |

Nearest lists offer "By distance" / "By price", Self / Served and Fuel toggles. Every
station line and alert carries a `🧭 Navigate` link (Google Maps directions URL, which the
phone opens in its maps app); opening a station also sends a Telegram venue pin.

## Station card and subscriptions

Tapping a station shows its price lists with one button per fuel. Tap to follow, tap again
to stop. Followed fuels get a "Thresholds" button.

Threshold rules, typed as text after `/soglia` or the Thresholds button:

| Text | Alert when |
|---|---|
| `sopra 1.85` | price above 1.850 |
| `sotto 1.70` | price below 1.700 |
| `1.70-1.85` | price outside the range |
| `nessuna` | every change |

Alerts ride on the observatory sync: `fuel.station.fuel._notify_followers` is extended to
message every Telegram subscription whose rule the new price crosses. No extra cron.

## Configuration

1. Install, then follow the `telegram_bot` README: token in Settings > Telegram, then
   Fuel Prices > Configuration > Register Telegram Webhook.
2. Settings > Telegram > Fuel Prices: number of nearest stations (default 10).

## Models

| Model | Purpose |
|---|---|
| `telegram.chat` (extended) | preferred fuel and mode, last location, conversation state, subscriptions |
| `fuel.telegram.subscription` | chat × price list, `above_price`, `below_price` |
| `fuel.station._nearest`, `fuel.station.fuel._nearest` | bounding box on indexed coordinates, haversine ranking |

## Menus

Fuel Prices > Telegram > Chats, Subscriptions. Fuel Prices > Configuration > Register
Telegram Webhook.

## Changelog

### 19.0.1.1.0

- Ask self service or served after the fuel choice, once per chat.
- Nearest stations and search results arrive as one card per station: price with a
  medal for the three cheapest, station, address, distance, time, Navigate and Station
  buttons; a closing message carries the order, mode and fuel toggles.

### 19.0.1.0.0

- Initial release.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
