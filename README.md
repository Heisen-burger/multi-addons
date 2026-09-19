# multi-addons

[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

Odoo 19 addons by STeSI Consulting. Branch `19.0` targets Odoo 19.0; each module carries its
own README, license and changelog.

## Modules

| Module | Summary | License |
|---|---|---|
| [fuel_price_observatory](fuel_price_observatory/) | Italian fuel prices from the MIMIT observatory: history, min/max, change alerts | OPL-1 |
| [telegram_bot](telegram_bot/) | Telegram Bot API client, webhook and command routing for other modules to extend | OPL-1 |
| [fuel_price_telegram](fuel_price_telegram/) | Telegram bot: nearest fuel prices, subscriptions with thresholds, change alerts | OPL-1 |

## Installation

Clone the repository, add its path to `addons_path`, update the app list and install the
modules you need.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
