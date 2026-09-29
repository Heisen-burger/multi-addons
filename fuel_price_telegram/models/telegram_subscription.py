# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from collections import defaultdict
from html import escape

from odoo import _, api, fields, models
from odoo.tools import float_compare

MAX_LINES = 15
MAX_BUTTONS = 5


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
        """Message every chat whose thresholds the changes cross, one message per chat."""
        by_fuel = defaultdict(lambda: self.browse())
        for sub in self.search([('station_fuel_id', 'in', changes.station_fuel_id.ids)]):
            by_fuel[sub.station_fuel_id.id] |= sub
        per_chat = defaultdict(lambda: self.env['fuel.price'])
        for change in changes:
            for sub in by_fuel.get(change.station_fuel_id.id, self.browse()):
                if sub._should_notify(change.price):
                    per_chat[sub.chat_id] |= change
        for chat, rows in per_chat.items():
            chat = chat.with_context(lang=chat._odoo_lang())
            if len(rows) == 1:
                self._notify_one(chat, rows)
            else:
                self._notify_many(chat, rows)

    def _change_row(self, change, with_station=True):
        """One monospaced line: old price, arrow, new price, then what moved."""
        handler = self.env['telegram.handler.fuel']
        arrow = "▲" if change.price > change.previous_price else "▼"
        row = "%7s → %7s %s" % (handler._fmt_price(change.previous_price),
                                handler._fmt_price(change.price), arrow)
        label = handler._short(handler._fuel_label(change.station_fuel_id), 16)
        if with_station:
            label = "%s · %s" % (handler._short(change.station_fuel_id.station_id.name, 18), label)
        return row, label

    def _notify_one(self, chat, change):
        handler = self.env['telegram.handler.fuel']
        station = change.station_fuel_id.station_id
        row, label = self._change_row(change, with_station=False)
        station_label = _("⛽ Station")
        history_label = _("📈 History")
        header = _("⛽ %(station)s · %(fuel)s", station=station.name, fuel=label)
        text = "%s\n%s\n🕒 %s" % (escape(header), handler._block([row]),
                                 handler._when(change.date_communicated))
        chat._say(text, keyboard=[[{'text': station_label, 'callback_data': 'st:%s' % station.id},
                                   {'text': history_label, 'callback_data': 'hist:%s' % station.id}]])

    def _notify_many(self, chat, changes):
        """One digest when a sync moves several prices the chat follows."""
        handler = self.env['telegram.handler.fuel']
        changes = changes.sorted(lambda c: (c.station_fuel_id.station_id.name, c.station_fuel_id.fuel_type))
        header = _("⛽ %s prices changed") % len(changes)
        lines = []
        for change in changes[:MAX_LINES]:
            row, label = self._change_row(change)
            lines.append(row)
            lines.append("  %s" % label)
        if len(changes) > MAX_LINES:
            lines.append(_("and %s more") % (len(changes) - MAX_LINES))
        body = handler._block(lines)
        if len(changes) > 4:
            body = "<blockquote expandable>%s</blockquote>" % body
        buttons = [{'text': "⛽ %s" % handler._short(station.name, 18), 'callback_data': 'st:%s' % station.id}
                   for station in changes.station_fuel_id.station_id[:MAX_BUTTONS]]
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        text = "%s\n%s\n🕒 %s" % (escape(header), body, handler._when(changes[0].date_communicated))
        chat._say(text, keyboard=keyboard)
