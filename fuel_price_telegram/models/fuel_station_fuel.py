# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import api, models

from .fuel_station import box_domain, haversine_km


class FuelStationFuel(models.Model):
    _inherit = 'fuel.station.fuel'

    @api.model
    def _nearest(self, lat, lng, fuel_type, is_self, limit=10):
        """Return [(km, price list)] for one fuel and service mode, nearest first."""
        base = [('fuel_type', '=', fuel_type), ('is_self', '=', is_self),
                ('current_price', '>', 0), ('station_id.active', '=', True)]
        for box in (0.3, 1.0):
            records = self.search(base + box_domain(lat, lng, box))
            if len(records) >= limit:
                break
        ranked = sorted(((haversine_km(lat, lng, r.latitude, r.longitude), r) for r in records),
                        key=lambda pair: pair[0])
        return ranked[:limit]

    def _notify_followers(self, changes):
        super()._notify_followers(changes)
        if changes:
            self.env['fuel.telegram.subscription']._notify(changes)
