# Fuel Price Observatory

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

Italian fuel prices from the MIMIT observatory (Osservatorio prezzi carburanti) inside Odoo:
every station, every fuel, a history of each price change, and chatter alerts for the price
lists you follow.

## Features

- **Price lists** (`fuel.station.fuel`): one record per station, fuel and service mode
  (self / served) with the current price, its communication date, and the historical
  minimum and maximum with their dates.
- **Price history** (`fuel.price`): one row per price change, with the previous price.
  Re-communications at the same price update the date only.
- **Stations** (`fuel.station`): brand, manager, type, address, city, province, coordinates.
- **Alerts**: follow a price list from its chatter. Each price change posts a message with
  the old and new price; followers receive it by email or in their Odoo inbox according to
  their own notification preference.
- **Two scheduled jobs** plus manual triggers under *Fuel Prices > Configuration*.

## Data sources

| Source | Endpoint | Cadence | Content |
|---|---|---|---|
| Observatory app API | `POST https://carburanti.mise.gov.it/ospzApi/search/servicearea` with body `{}` | every 30 minutes | all stations with current fuels (~21,700 stations, ~93,000 prices, 12 MB) |
| Registry CSV | `https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv` | daily at 07:00 UTC | manager, station type, street, city, province |

The API carries communications up to the minute of the call. The CSV lags about one day,
so the module uses it only for the descriptive fields the API does not split out.

When the single API call fails, the sync falls back to one call per region
(`GET .../ospzApi/registry/region`). The API is the one used by the official mobile app and
is not documented by MIMIT: if it changes, the price cron logs a warning and the data stays
at the last successful sync.

## How the sync works

1. Download the full dump.
2. Create missing stations and price lists.
3. For each fuel, compare the communication id (`fuels[].id`) with the one stored:
   - same id: nothing to do;
   - new id, same price: update the communication date;
   - new id, different price: update the price list and append a history row.
4. Post a chatter message on every changed price list that has followers.

The first run inserts every station, price list and one history row each. Later runs write
only what changed.

## Models

| Model | Purpose | Key fields |
|---|---|---|
| `fuel.station` | station registry | `mimit_id` (unique), `name`, `brand`, `manager`, `station_type`, `street`, `city`, `province`, `latitude`, `longitude`, `active` |
| `fuel.station.fuel` | price list, followable (`mail.thread`) | `station_id`, `fuel_type`, `is_self`, `current_price`, `current_date`, `mimit_price_id`, `min_price`, `min_date`, `max_price`, `max_date` |
| `fuel.price` | history, insert only | `station_fuel_id`, `price`, `previous_price`, `date_communicated`, `mimit_price_id` |

## Menus

*Fuel Prices*: Price Lists (default view, sorted by price, filter *Followed by Me*),
Stations, Price History (list and line graph), Configuration (Update Prices, Update
Stations; administrators only).

## Access rights

| Model | Internal user | Administrator |
|---|---|---|
| `fuel.station`, `fuel.station.fuel`, `fuel.price` | read | read, write, create, delete |

Following a price list needs read access only.

## Installation

Add the repository to `addons_path`, update the app list and install
*Fuel Price Observatory*. Run *Configuration > Update Prices* once, or wait for the cron.

## Tests

```bash
python3 odoo-bin -c odoo19.conf -d test_fpo19 -i fuel_price_observatory --test-enable \
  --stop-after-init --max-cron-threads=0
```

Tests patch the two fetch methods with the samples in `tests/data/`.

## Changelog

### 19.0.1.0.2

- Add Italian translation and the `.pot` template.

### 19.0.1.0.1

- Fix min/max dates on price ties: sort history rows before picking them.

### 19.0.1.0.0

- Initial release: stations, price lists, price history, follower alerts, API and CSV sync.

## Credits

### Authors

- STeSI Consulting

### Contributors

- Michele Di Croce <dicroce.m@stesi.consulting>
