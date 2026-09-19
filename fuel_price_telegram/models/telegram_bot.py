# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from html import escape

from odoo import _, api, models

STATION_TZ = 'Europe/Rome'


class TelegramBot(models.AbstractModel):
    _inherit = 'telegram.bot'

    @api.model
    def _commands(self):
        return super()._commands() + [
            ('vicini', _("Prices around your last location")),
            ('carburante', _("Change the fuel you are looking for")),
            ('lista', _("Manage your subscriptions")),
            ('prezzi', _("Current prices of your subscriptions")),
            ('soglia', _("Set alert thresholds")),
            ('stop', _("Remove every subscription")),
            ('aiuto', _("Help")),
        ]

    @api.model
    def _maps_link(self, station):
        return "https://www.google.com/maps/dir/?api=1&destination=%s,%s" % (station.latitude, station.longitude)

    @api.model
    def _navigate(self, station):
        return '<a href="%s">🧭 %s</a>' % (escape(self._maps_link(station)), escape(_("Navigate")))

    @api.model
    def _fmt_station_dt(self, value):
        return self._fmt_dt(value, tz=STATION_TZ)
