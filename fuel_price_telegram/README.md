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
| `/storico` | last price changes of the station you opened last |
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

1. Install, then Fuel Prices > Telegram > Bots: new bot, kind *Fuel prices*, token from
   @BotFather, access code if wanted, *Register Webhook*.
2. Settings > Fuel Prices: number of nearest stations (default 10).

## Models

| Model | Purpose |
|---|---|
| `telegram.handler.fuel` | the whole conversation, bound to bots of kind *Fuel prices* |
| `telegram.chat` (extended) | preferred fuel and mode, last location, conversation state, subscriptions |
| `fuel.telegram.subscription` | chat × price list, `above_price`, `below_price` |
| `fuel.station._nearest`, `fuel.station.fuel._nearest` | bounding box on indexed coordinates, haversine ranking |

## Menus

Fuel Prices > Telegram > Bots, Chats, Subscriptions.

## Changelog

### 19.0.2.2.1

- Fuel choice lists every fuel on sale, not the six most common: Metano and the other
  blends were missing. Benzina, Gasolio, GPL and Metano lead, the rest follows by how many
  stations sell it.

### 19.0.2.2.0

- Price lines carry the previous price, `(prec. 1.849)`, instead of the difference.

### 19.0.2.1.1

- Station card marks a fuel with no recorded change, so a missing move reads as missing
  data rather than a bug. The observatory only knows the prices it has seen since it
  started syncing: MIMIT publishes no past history.

### 19.0.2.1.0

- Every price the bot sends carries the price before it: nearest cards, station card,
  `/lista`, `/prezzi`.
- History: a button on the station card and the `/storico` command list the last twelve
  changes of that station, each with old and new price.

### 19.0.2.0.0

- Multi-bot base: conversation moved to `telegram.handler.fuel`, bots of kind *Fuel
  prices*; the migration marks the existing bot. Register its webhook again.

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
