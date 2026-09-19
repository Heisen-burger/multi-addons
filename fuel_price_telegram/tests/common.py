# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo.fields import Command

from odoo.addons.telegram_bot.tests.common import TelegramCase


class FuelTelegramCase(TelegramCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot.kind = 'fuel'
        cls.Sub = cls.env['fuel.telegram.subscription']
        cls.Station = cls.env['fuel.station']
        cls.stations = cls.Station.create([
            cls._station(9001, "ENI DUOMO", "MILANO", 45.4642, 9.1900, benzina=1.899, gasolio=1.799),
            cls._station(9002, "IP NAVIGLI", "MILANO", 45.4500, 9.1700, benzina=1.879, gasolio=1.749),
            cls._station(9003, "Q8 MONZA", "MONZA", 45.5845, 9.2744, benzina=1.859, gasolio=1.769),
            cls._station(9004, "TAMOIL TORINO", "TORINO", 45.0703, 7.6869, benzina=1.849, gasolio=1.739),
        ])
        cls.duomo, cls.navigli, cls.monza, cls.torino = cls.stations

    @staticmethod
    def _station(mimit_id, name, city, lat, lng, **prices):
        return {
            'mimit_id': mimit_id, 'name': name, 'city': city, 'province': city[:2],
            'brand': name.split()[0], 'latitude': lat, 'longitude': lng,
            'fuel_ids': [Command.create({
                'fuel_type': fuel.capitalize(), 'is_self': True, 'current_price': price,
                'current_date': '2026-09-18 06:00:00', 'mimit_price_id': mimit_id * 10 + i,
                'price_ids': [Command.create({'price': price, 'previous_price': 0.0,
                                              'date_communicated': '2026-09-18 06:00:00',
                                              'mimit_price_id': mimit_id * 10 + i})],
            }) for i, (fuel, price) in enumerate(prices.items())],
        }

    def fuel(self, station, fuel_type):
        return station.fuel_ids.filtered(lambda f: f.fuel_type == fuel_type)
