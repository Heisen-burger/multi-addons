# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from collections import defaultdict
from html import escape

from odoo import _, api, fields, models
from odoo.tools import float_compare


class TelegramSubscription(models.Model):
    _name = 'fuel.telegram.subscription'
    _description = "Telegram Price Subscription"
    _order = 'current_price, id'

    chat_id = fields.Many2one('telegram.chat', required=True, index=True, ondelete='cascade')
    station_fuel_id = fields.Many2one('fuel.station.fuel', string="Price List", required=True,
                                      index=True, ondelete='cascade')
    above_price = fields.Float(digits=(6, 3), help="Alert when the price goes above this value. 0 disables it.")
    below_price = fields.Float(digits=(6, 3), help="Alert when the price goes below this value. 0 disables it.")
    active = fields.Boolean(default=True)
    station_id = fields.Many2one(related='station_fuel_id.station_id')
    fuel_type = fields.Char(related='station_fuel_id.fuel_type')
    is_self = fields.Boolean(related='station_fuel_id.is_self')
    current_price = fields.Float(related='station_fuel_id.current_price', store=True)

    _chat_fuel_unique = models.Constraint(
        'unique (chat_id, station_fuel_id)',
        "This chat already follows this price list.",
    )

    def _should_notify(self, price):
        self.ensure_one()
        if not self.above_price and not self.below_price:
            return True
        return bool(
            (self.above_price and float_compare(price, self.above_price, 3) > 0)
            or (self.below_price and float_compare(price, self.below_price, 3) < 0)
        )

    def _threshold_label(self):
        self.ensure_one()
        if self.above_price and self.below_price:
            return _("outside %(low).3f-%(high).3f", low=self.below_price, high=self.above_price)
        if self.above_price:
            return _("above %.3f") % self.above_price
        if self.below_price:
            return _("below %.3f") % self.below_price
        return _("every change")

    @api.model
    def _notify(self, changes):
        """Send one Telegram message per subscription whose threshold the change crosses."""
        handler = self.env['telegram.handler.fuel']
        by_fuel = defaultdict(lambda: self.browse())
        for sub in self.search([('station_fuel_id', 'in', changes.station_fuel_id.ids)]):
            by_fuel[sub.station_fuel_id.id] |= sub
        for change in changes:
            for sub in by_fuel.get(change.station_fuel_id.id, self.browse()):
                if not sub._should_notify(change.price):
                    continue
                chat = sub.chat_id.with_context(lang=sub.chat_id._odoo_lang())
                bot = chat.bot_id
                fuel = change.station_fuel_id
                station = fuel.station_id
                text = "⛽ <b>%s</b>\n%s: %.3f → <b>%.3f</b> (%+.3f)\n%s · %s" % (
                    escape(station.name), escape(handler._fuel_label(fuel)),
                    change.previous_price, change.price, change.price - change.previous_price,
                    bot._fmt_station_dt(change.date_communicated), bot._navigate(station),
                )
                station_label = _("Station")
                chat._say(text, keyboard=[[{'text': station_label, 'callback_data': 'st:%s' % station.id}]])
