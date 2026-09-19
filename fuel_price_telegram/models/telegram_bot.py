# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from html import escape

from odoo import _, fields, models

STATION_TZ = 'Europe/Rome'


class TelegramBot(models.Model):
    _inherit = 'telegram.bot'

    kind = fields.Selection(selection_add=[('fuel', "Fuel prices")], ondelete={'fuel': 'set default'})

    def _maps_link(self, station):
        return "https://www.google.com/maps/dir/?api=1&destination=%s,%s" % (station.latitude, station.longitude)

    def _navigate(self, station):
        return '<a href="%s">🧭 %s</a>' % (escape(self._maps_link(station)), escape(_("Navigate")))

    def _fmt_station_dt(self, value):
        return self._fmt_dt(value, tz=STATION_TZ)
