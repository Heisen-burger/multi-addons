# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging
from datetime import datetime, timezone

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

API_BASE = 'https://carburanti.mise.gov.it/ospzApi'
SEARCH_URL = API_BASE + '/search/servicearea'
REGION_URL = API_BASE + '/registry/region'
PRICE_DIGITS = 3


class FuelStationFuel(models.Model):
    _name = 'fuel.station.fuel'
    _description = "Fuel Station Price List"
    _inherit = ['mail.thread']
    _order = 'current_price, id'
    _rec_names_search = ['station_id.name', 'fuel_type', 'city']

    station_id = fields.Many2one('fuel.station', required=True, index=True, ondelete='cascade')
    fuel_type = fields.Char(required=True, index=True, help="Fuel name as published by MIMIT.")
    fuel_code = fields.Integer(help="MIMIT fuel identifier (1 petrol, 2 diesel, 3 CNG, 4 LPG, ...).")
    is_self = fields.Boolean("Self Service")
    current_price = fields.Float(digits=(6, PRICE_DIGITS))
    current_date = fields.Datetime(help="When the station communicated the current price.")
    previous_price = fields.Float(digits=(6, PRICE_DIGITS),
                                  help="Price before the last change, 0 until the price moves once.")
    mimit_price_id = fields.Integer("MIMIT Price ID",
                                    help="Identifier of the last price communication seen.")
    min_price = fields.Float(digits=(6, PRICE_DIGITS), compute='_compute_min_max', store=True)
    min_date = fields.Datetime(compute='_compute_min_max', store=True)
    max_price = fields.Float(digits=(6, PRICE_DIGITS), compute='_compute_min_max', store=True)
    max_date = fields.Datetime(compute='_compute_min_max', store=True)
    price_ids = fields.One2many('fuel.price', 'station_fuel_id', string="History")
    brand = fields.Char(related='station_id.brand', store=True)
    city = fields.Char(related='station_id.city', store=True)
    province = fields.Char(related='station_id.province', store=True)
    latitude = fields.Float(related='station_id.latitude', store=True)
    longitude = fields.Float(related='station_id.longitude', store=True)

    _key_unique = models.Constraint(
        'unique (station_id, fuel_type, is_self)',
        "This station already has a price list for this fuel and service mode.",
    )

    @api.depends('station_id.name', 'fuel_type', 'is_self')
    def _compute_display_name(self):
        for rec in self:
            mode = _("Self") if rec.is_self else _("Served")
            rec.display_name = f"{rec.station_id.name} - {rec.fuel_type} {mode}"

    @api.depends('price_ids.price')
    def _compute_min_max(self):
        # newest first, so min()/max() keep the most recent row on ties; the O2M cache
        # appends rows in creation order, so sort here instead of trusting _order
        for rec in self:
            prices = rec.price_ids.sorted(key=lambda p: (p.date_communicated, p.id), reverse=True)
            low = min(prices, key=lambda p: p.price, default=None)
            high = max(prices, key=lambda p: p.price, default=None)
            rec.min_price = low.price if low else 0.0
            rec.min_date = low.date_communicated if low else False
            rec.max_price = high.price if high else 0.0
            rec.max_date = high.date_communicated if high else False

    # ------------------------------------------------------------------
    # MIMIT API
    # ------------------------------------------------------------------
    @api.model
    def _fetch_api(self):
        """Return the list of stations with their fuels from the observatory API.

        One POST with an empty body returns the whole country (12 MB, ~30 s). When it
        fails the method falls back to one call per region. Tests patch this method.
        """
        try:
            response = requests.post(SEARCH_URL, json={}, timeout=120)
            response.raise_for_status()
            return response.json()['results']
        except (requests.RequestException, KeyError, ValueError) as error:
            _logger.warning("Fuel API: full dump failed (%s), falling back to regions", error)
        regions = requests.get(REGION_URL, timeout=30)
        regions.raise_for_status()
        results = []
        for region in regions.json()['results']:
            response = requests.post(SEARCH_URL, json={'region': region['id']}, timeout=60)
            response.raise_for_status()
            results.extend(response.json()['results'])
        return results

    @staticmethod
    def _parse_date(value):
        """'2026-09-18T21:46:12+02:00' to a naive UTC datetime, or now when missing."""
        if not value:
            return fields.Datetime.now()
        return datetime.fromisoformat(value).astimezone(timezone.utc).replace(tzinfo=None)

    @api.model
    def _cron_sync_prices(self):
        self.env['fuel.type']._sync_fuel_types()
        results = self._fetch_api()
        Station = self.env['fuel.station'].with_context(active_test=False)
        Price = self.env['fuel.price']

        stations = {r['mimit_id']: r['id'] for r in Station.search_read([], ['mimit_id'])}
        new_stations = Station.create([{
            'mimit_id': r['id'],
            'name': r.get('name') or r.get('brand') or str(r['id']),
            'brand': r.get('brand'),
            'address': r.get('address'),
            'latitude': (r.get('location') or {}).get('lat', 0.0),
            'longitude': (r.get('location') or {}).get('lng', 0.0),
        } for r in results if r['id'] not in stations])
        stations.update({s.mimit_id: s.id for s in new_stations})

        current = {
            (row['station_id'][0], row['fuel_type'], row['is_self']): row
            for row in self.search_read([], ['station_id', 'fuel_type', 'is_self',
                                             'current_price', 'mimit_price_id'])
        }
        # a station can list the same (fuel, self) twice: keep the latest communication
        incoming = {}
        for station in results:
            station_id = stations[station['id']]
            date = self._parse_date(station.get('insertDate'))
            for fuel in station.get('fuels') or []:
                key = (station_id, fuel['name'], bool(fuel['isSelf']))
                if key not in incoming or fuel['id'] > incoming[key][0]['id']:
                    incoming[key] = (fuel, date)

        to_create = []
        history = []
        touched = []
        for key, (fuel, date) in incoming.items():
            price = float(fuel['price'])
            row = current.get(key)
            if row is None:
                to_create.append({
                    'station_id': key[0],
                    'fuel_type': fuel['name'],
                    'fuel_code': fuel.get('fuelId', 0),
                    'is_self': key[2],
                    'current_price': price,
                    'current_date': date,
                    'mimit_price_id': fuel['id'],
                    'price_ids': [fields.Command.create({
                        'price': price,
                        'previous_price': 0.0,
                        'date_communicated': date,
                        'mimit_price_id': fuel['id'],
                    })],
                })
                continue
            if fuel['id'] == row['mimit_price_id']:
                continue
            vals = {'current_date': date, 'mimit_price_id': fuel['id']}
            if float_compare(price, row['current_price'], precision_digits=PRICE_DIGITS):
                vals['current_price'] = price
                vals['previous_price'] = row['current_price']
                history.append({
                    'station_fuel_id': row['id'],
                    'price': price,
                    'previous_price': row['current_price'],
                    'date_communicated': date,
                    'mimit_price_id': fuel['id'],
                })
            touched.append((row['id'], vals))

        created = self.create(to_create)
        # ponytail: one write per changed row; batch through SQL if runs get slow
        for rec_id, vals in touched:
            self.browse(rec_id).write(vals)
        changes = Price.create(history)
        self._notify_followers(changes)
        _logger.info("Fuel prices: %s new price lists, %s updated, %s price changes",
                     len(created), len(touched), len(changes))
        return True

    def _notify_followers(self, changes):
        """Post one chatter message per changed price list that has followers."""
        if not changes:
            return
        followed = {
            res_id for (res_id,) in self.env['mail.followers'].sudo()._read_group(
                [('res_model', '=', self._name), ('res_id', 'in', changes.station_fuel_id.ids)],
                groupby=['res_id'],
            )
        }
        for change in changes.filtered(lambda c: c.station_fuel_id.id in followed):
            delta = change.price - change.previous_price
            body = Markup("<p>%s</p>") % _(
                "%(fuel)s: price changed from %(old).3f to %(new).3f (%(delta)+.3f) on %(date)s",
                fuel=change.station_fuel_id.display_name,
                old=change.previous_price,
                new=change.price,
                delta=delta,
                date=fields.Datetime.context_timestamp(self, change.date_communicated).strftime('%d/%m/%Y %H:%M'),
            )
            change.station_fuel_id.message_post(
                body=body,
                subtype_xmlid='fuel_price_observatory.mt_price_change',
            )
