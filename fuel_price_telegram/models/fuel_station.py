# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from math import asin, cos, radians, sin, sqrt

from odoo import api, models

EARTH_KM = 6371.0


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(a))


def box_domain(lat, lng, box):
    return [('latitude', '>=', lat - box), ('latitude', '<=', lat + box),
            ('longitude', '>=', lng - box), ('longitude', '<=', lng + box)]


class FuelStation(models.Model):
    _inherit = 'fuel.station'

    @api.model
    def _nearest(self, lat, lng, limit=10):
        """Return [(km, station)] sorted by distance, stations with prices only.

        A 0.3 degree box (~30 km) is tried first, then 1 degree when it holds fewer
        stations than asked.
        """
        for box in (0.3, 1.0):
            stations = self.search(box_domain(lat, lng, box) + [('fuel_ids.current_price', '>', 0)])
            if len(stations) >= limit:
                break
        ranked = sorted(((haversine_km(lat, lng, s.latitude, s.longitude), s) for s in stations),
                        key=lambda pair: pair[0])
        return ranked[:limit]
