# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import re
from html import escape

from odoo import _, api, fields, models

NUMBER = r'(\d+(?:[.,]\d+)?)'
RE_RANGE = re.compile(r'^\s*' + NUMBER + r'\s*[-–]\s*' + NUMBER + r'\s*$')
RE_ABOVE = re.compile(r'^\s*(?:sopra|above|>)\s*' + NUMBER + r'\s*$', re.I)
RE_BELOW = re.compile(r'^\s*(?:sotto|below|<)\s*' + NUMBER + r'\s*$', re.I)
RESET_WORDS = ('nessuna', 'none', 'no', '0', 'reset')
ALL_FUELS = '*'


class TelegramChat(models.Model):
    _inherit = 'telegram.chat'

    state = fields.Selection(selection_add=[('threshold', "Waiting for threshold")],
                             ondelete={'threshold': 'set default'})
    pending_subscription_id = fields.Many2one('fuel.telegram.subscription', ondelete='set null',
                                              help="Subscription whose threshold the next message sets.")
    last_station_id = fields.Many2one('fuel.station', ondelete='set null')
    fuel_type = fields.Char(help="Fuel used when the chat sends a location. '*' means every fuel.")
    is_self = fields.Boolean("Self Service", default=True)
    mode_chosen = fields.Boolean(help="The chat answered the self/served question at least once.")
    last_latitude = fields.Float(digits=(10, 6))
    last_longitude = fields.Float(digits=(10, 6))
    subscription_ids = fields.One2many('fuel.telegram.subscription', 'chat_id', string="Subscriptions")
    subscription_count = fields.Integer(compute='_compute_subscription_count')

    @api.depends('subscription_ids')
    def _compute_subscription_count(self):
        for chat in self:
            chat.subscription_count = len(chat.subscription_ids)

    # ------------------------------------------------------------------
    # routing hooks
    # ------------------------------------------------------------------
    def _reset_state(self):
        self.write({'state': 'idle', 'pending_subscription_id': False})

    def _on_free_text(self, text):
        if self.state == 'threshold':
            return self._set_threshold(text)
        return self._search_stations(text)

    def _on_location(self, location):
        self.write({'last_latitude': location['latitude'], 'last_longitude': location['longitude']})
        if not self.fuel_type:
            return self._ask_fuel()
        if self.fuel_type != ALL_FUELS and not self.mode_chosen:
            return self._ask_mode()
        return self._send_nearest()

    # ------------------------------------------------------------------
    # callbacks
    # ------------------------------------------------------------------
    def _cb_st(self, arg, message):
        self._show_station(int(arg))

    def _cb_sub(self, arg, message):
        self._toggle_subscription(int(arg), message)

    def _cb_thr(self, arg, message):
        self._ask_threshold(int(arg))

    def _cb_thrst(self, arg, message):
        self._cmd_soglia(station_id=int(arg))

    def _cb_del(self, arg, message):
        self._remove_subscription(int(arg))

    def _cb_fuel(self, arg, message):
        if not arg:
            return self._ask_fuel()
        self.write({'fuel_type': arg})
        if arg != ALL_FUELS:
            return self._ask_mode()
        self._send_nearest_or_ask_location()

    def _cb_mode(self, arg, message):
        self.write({'is_self': arg == '1', 'mode_chosen': True})
        self._send_nearest_or_ask_location()

    def _send_nearest_or_ask_location(self):
        if self.last_latitude:
            self._send_nearest()
        else:
            self._say(_("Now send me your location."), reply_keyboard=self._location_keyboard())

    def _cb_near(self, arg, message):
        self._send_nearest(order=arg)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def _location_keyboard(self):
        return {'keyboard': [[{'text': _("📍 Send my location"), 'request_location': True}]],
                'resize_keyboard': True}

    def _cmd_start(self):
        self._say(_("Hi! Send me your location to see fuel prices around you, "
                    "or type a town name to search a station.\n"
                    "Open a station to follow one or more fuels: I will message you at every "
                    "price change, or only outside the thresholds you set.\n\n/aiuto for the commands."),
                  reply_keyboard=self._location_keyboard())

    def _cmd_aiuto(self):
        self._cmd_help()

    def _cmd_vicini(self):
        if not self.last_latitude:
            return self._say(_("Send me your location first."), reply_keyboard=self._location_keyboard())
        if not self.fuel_type:
            return self._ask_fuel()
        self._send_nearest()

    def _cmd_carburante(self):
        self._ask_fuel()

    def _cmd_lista(self):
        subs = self.subscription_ids
        if not subs:
            return self._say(_("No subscriptions yet. Send your location or a town name to find a station."))
        bot = self._bot()
        lines = []
        keyboard = []
        for index, sub in enumerate(subs, 1):
            fuel = sub.station_fuel_id
            lines.append("%s. <b>%s</b> %s: <b>%.3f</b> · %s\n   %s · %s" % (
                index, escape(fuel.station_id.name), escape(self._fuel_label(fuel)), fuel.current_price,
                bot._fmt_station_dt(fuel.current_date), escape(sub._threshold_label()),
                bot._navigate(fuel.station_id)))
            keyboard.append([
                {'text': "⚙️ %s" % index, 'callback_data': 'thr:%s' % sub.id},
                {'text': "🗑 %s" % index, 'callback_data': 'del:%s' % sub.id},
                {'text': "⛽ %s" % index, 'callback_data': 'st:%s' % fuel.station_id.id},
            ])
        self._say("\n".join(lines), keyboard=keyboard)

    def _cmd_prezzi(self):
        subs = self.subscription_ids
        if not subs:
            return self._say(_("No subscriptions yet. Send your location or a town name to find a station."))
        bot = self._bot()
        lines = []
        for sub in subs:
            fuel = sub.station_fuel_id
            last = self.env['fuel.price'].search([('station_fuel_id', '=', fuel.id)], limit=1)
            delta = " (%+.3f)" % (last.price - last.previous_price) if last.previous_price else ""
            lines.append("<b>%.3f</b>%s %s %s · %s · %s" % (
                fuel.current_price, delta, escape(fuel.station_id.name), escape(self._fuel_label(fuel)),
                bot._fmt_station_dt(fuel.current_date), bot._navigate(fuel.station_id)))
        self._say("\n".join(lines))

    def _cmd_soglia(self, station_id=None):
        subs = self.subscription_ids
        if station_id:
            subs = subs.filtered(lambda s: s.station_id.id == station_id)
        if not subs:
            return self._say(_("Follow a fuel first: open a station and tap the fuel."))
        if len(subs) == 1:
            return self._ask_threshold(subs.id)
        keyboard = [[{'text': "%s %s" % (s.station_id.name, self._fuel_label(s.station_fuel_id)),
                      'callback_data': 'thr:%s' % s.id}] for s in subs]
        self._say(_("Which subscription?"), keyboard=keyboard)

    def _cmd_stop(self):
        self.subscription_ids.write({'active': False})
        self.write({'pending_subscription_id': False})
        super()._cmd_stop()

    # ------------------------------------------------------------------
    # search and nearest
    # ------------------------------------------------------------------
    def _ask_fuel(self):
        groups = self.env['fuel.station.fuel']._read_group(
            [('current_price', '>', 0)], groupby=['fuel_type'], aggregates=['__count'],
            order='__count desc', limit=6)
        buttons = [{'text': fuel_type, 'callback_data': 'fuel:%s' % fuel_type} for fuel_type, _count in groups]
        keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        keyboard.append([{'text': _("All fuels"), 'callback_data': 'fuel:' + ALL_FUELS}])
        self._say(_("Which fuel are you looking for?"), keyboard=keyboard)

    def _ask_mode(self):
        self_label = _("Self service")
        served_label = _("Served")
        self._say(_("Self service or served?"), keyboard=[[
            {'text': "🤳 " + self_label, 'callback_data': 'mode:1'},
            {'text': "🧑‍🔧 " + served_label, 'callback_data': 'mode:0'},
        ]])

    def _limit(self):
        return int(self.env['ir.config_parameter'].sudo().get_param('fuel_telegram.nearest_limit', 10) or 10)

    def _station_buttons(self, station):
        navigate = _("🧭 Navigate")
        card = _("⛽ Station")
        return [[{'text': navigate, 'url': self._bot()._maps_link(station)},
                 {'text': card, 'callback_data': 'st:%s' % station.id}]]

    def _station_message(self, station, km=None, fuel=None, rank=None):
        """One card per station: price line (or every price), name, address, distance, time."""
        bot = self._bot()
        lines = []
        if fuel is not None:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "%s." % rank if rank else "")
            lines.append("%s <b>%.3f €</b> · %s" % (medal, fuel.current_price, escape(self._fuel_label(fuel))))
        lines.append("⛽ <b>%s</b> · %s" % (escape(station.name), escape(station.brand or "")))
        address = ", ".join(p for p in (station.street, station.city) if p) or station.address or ""
        distance = " · %.1f km" % km if km is not None else ""
        lines.append("📍 %s%s" % (escape(address), distance))
        if fuel is not None:
            lines.append("🕒 %s" % bot._fmt_station_dt(fuel.current_date))
        else:
            for row in station.fuel_ids.filtered('current_price'):
                lines.append("• %s <b>%.3f €</b> · %s" % (escape(self._fuel_label(row)), row.current_price,
                                                         bot._fmt_station_dt(row.current_date)))
        return "\n".join(lines)

    def _send_nearest(self, order='price'):
        lat, lng = self.last_latitude, self.last_longitude
        all_fuels = self.fuel_type == ALL_FUELS
        cards = []
        if all_fuels:
            cards = [(station, km, None) for km, station in self.env['fuel.station']._nearest(lat, lng, self._limit())]
        else:
            ranked = self.env['fuel.station.fuel']._nearest(lat, lng, self.fuel_type, self.is_self, self._limit())
            if order == 'dist':
                ranked.sort(key=lambda pair: pair[0])
            else:
                ranked.sort(key=lambda pair: (pair[1].current_price, pair[0]))
            cards = [(fuel.station_id, km, fuel) for km, fuel in ranked]
        if not cards:
            change_fuel = _("Change fuel")
            return self._say(_("No station with %s within 100 km of this point.") % escape(self.fuel_type or ""),
                             keyboard=[[{'text': change_fuel, 'callback_data': 'fuel:'}]])
        # labels first: a parenthesis opened right after a _() call confuses the term extractor
        by_distance = order == 'dist' or all_fuels
        fuel_label = _("All fuels") if all_fuels else self.fuel_type
        order_label = _("by distance") if by_distance else _("by price")
        header = _("%(fuel)s %(mode)s, %(order)s", fuel=fuel_label,
                   mode="" if all_fuels else self._mode_label(), order=order_label)
        self._say("<b>%s</b>" % escape(header))
        for rank, (station, km, fuel) in enumerate(cards, 1):
            self._say(self._station_message(station, km=km, fuel=fuel, rank=None if by_distance else rank),
                      keyboard=self._station_buttons(station))
        toggle_label = _("💶 By price") if by_distance else _("📏 By distance")
        mode_label = _("Served") if self.is_self else _("Self service")
        fuel_button = _("Fuel")
        footer = _("Change the list:")
        keyboard = [[{'text': fuel_button, 'callback_data': 'fuel:'}]]
        if not all_fuels:
            keyboard[0].insert(0, {'text': mode_label, 'callback_data': 'mode:0' if self.is_self else 'mode:1'})
            keyboard[0].insert(0, {'text': toggle_label, 'callback_data': 'near:price' if by_distance else 'near:dist'})
        self._say(footer, keyboard=keyboard)

    def _search_stations(self, text):
        # never name this _search: it would shadow the ORM method
        stations = self.env['fuel.station'].search(
            ['&', ('fuel_ids.current_price', '>', 0), '|', ('city', 'ilike', text), ('name', 'ilike', text)],
            limit=10, order='city, name')
        if not stations:
            return self._say(_("No station found for \"%s\". Try a town name or send your location.") % escape(text),
                             reply_keyboard=self._location_keyboard())
        for station in stations:
            self._say(self._station_message(station), keyboard=self._station_buttons(station))

    # ------------------------------------------------------------------
    # station card and subscriptions
    # ------------------------------------------------------------------
    def _fuel_label(self, fuel):
        return "%s %s" % (fuel.fuel_type, _("Self") if fuel.is_self else _("Served"))

    def _mode_label(self):
        return _("Self") if self.is_self else _("Served")

    def _station_keyboard(self, station):
        followed = set(self.subscription_ids.mapped('station_fuel_id').ids)
        navigate = _("🧭 Navigate")
        keyboard = [[{'text': navigate, 'url': self._bot()._maps_link(station)}]]
        keyboard += [[{'text': "%s %s" % ("✅" if fuel.id in followed else "➕", self._fuel_label(fuel)),
                       'callback_data': 'sub:%s' % fuel.id}]
                     for fuel in station.fuel_ids.filtered('current_price')]
        if followed & set(station.fuel_ids.ids):
            keyboard.append([{'text': _("⚙️ Thresholds"), 'callback_data': 'thrst:%s' % station.id}])
        return keyboard

    def _show_station(self, station_id):
        station = self.env['fuel.station'].browse(station_id).exists()
        if not station:
            return self._say(_("Station not found."))
        self.write({'last_station_id': station.id})
        bot = self._bot()
        address = ", ".join(p for p in (station.street, station.city) if p) or station.address or ""
        bot._call('sendVenue', chat_id=self.chat_id, latitude=station.latitude, longitude=station.longitude,
                  title=station.name, address=address)
        lines = ["<b>%s</b> · %s" % (escape(station.name), escape(station.brand or "")),
                 "📍 " + escape(", ".join(p for p in (station.street, station.city, station.province) if p)
                               or station.address or ""),
                 ""]
        for fuel in station.fuel_ids.filtered('current_price'):
            lines.append("%s: <b>%.3f</b> · %s" % (escape(self._fuel_label(fuel)), fuel.current_price,
                                                   bot._fmt_station_dt(fuel.current_date)))
        lines += ["", escape(_("Tap a fuel to follow it, tap again to stop."))]
        self._say("\n".join(lines), keyboard=self._station_keyboard(station))

    def _toggle_subscription(self, station_fuel_id, message):
        fuel = self.env['fuel.station.fuel'].browse(station_fuel_id).exists()
        if not fuel:
            return self._say(_("Price list not found."))
        Sub = self.env['fuel.telegram.subscription'].with_context(active_test=False)
        sub = Sub.search([('chat_id', '=', self.id), ('station_fuel_id', '=', fuel.id)], limit=1)
        if sub and sub.active:
            sub.write({'active': False})
            self._say(_("Unfollowed %s.") % escape(fuel.display_name))
        else:
            if sub:
                sub.write({'active': True, 'above_price': 0, 'below_price': 0})
            else:
                Sub.create({'chat_id': self.id, 'station_fuel_id': fuel.id})
            self._say(_("Following %s: you get a message at every price change. "
                        "Set thresholds with /soglia.") % escape(fuel.display_name))
        self.invalidate_recordset(['subscription_ids'])
        self._bot()._call('editMessageReplyMarkup', chat_id=self.chat_id, message_id=message['message_id'],
                          reply_markup={'inline_keyboard': self._station_keyboard(fuel.station_id)})

    def _remove_subscription(self, sub_id):
        sub = self.subscription_ids.filtered(lambda s: s.id == sub_id)
        if sub:
            name = sub.station_fuel_id.display_name
            sub.write({'active': False})
            self._say(_("Unfollowed %s.") % escape(name))
        self.invalidate_recordset(['subscription_ids'])
        if self.subscription_ids:
            self._cmd_lista()

    def _ask_threshold(self, sub_id):
        sub = self.env['fuel.telegram.subscription'].browse(sub_id).exists()
        if not sub or sub.chat_id != self:
            return self._say(_("Subscription not found."))
        self.write({'state': 'threshold', 'pending_subscription_id': sub.id})
        self._say(_("%(name)s, now %(price).3f, alert %(rule)s.\n"
                    "Send the new rule:\n"
                    "<code>sopra 1.85</code> alert above 1.85\n"
                    "<code>sotto 1.70</code> alert below 1.70\n"
                    "<code>1.70-1.85</code> alert outside the range\n"
                    "<code>nessuna</code> alert at every change",
                    name=escape(sub.station_fuel_id.display_name), price=sub.current_price,
                    rule=escape(sub._threshold_label())))

    def _set_threshold(self, text):
        sub = self.pending_subscription_id
        if not sub or not sub.active:
            self._reset_state()
            return self._say(_("Subscription not found."))
        value = text.lower().replace(',', '.')
        vals = None
        if value.strip() in RESET_WORDS:
            vals = {'above_price': 0, 'below_price': 0}
        elif match := RE_RANGE.match(value):
            low, high = sorted(float(v) for v in match.groups())
            vals = {'below_price': low, 'above_price': high}
        elif match := RE_ABOVE.match(value):
            vals = {'above_price': float(match.group(1)), 'below_price': 0}
        elif match := RE_BELOW.match(value):
            vals = {'below_price': float(match.group(1)), 'above_price': 0}
        if vals is None:
            return self._say(_("I did not understand. Examples: <code>sopra 1.85</code>, "
                               "<code>sotto 1.70</code>, <code>1.70-1.85</code>, <code>nessuna</code>."))
        sub.write(vals)
        self._reset_state()
        self._say(_("%(name)s: alert %(rule)s.", name=escape(sub.station_fuel_id.display_name),
                    rule=escape(sub._threshold_label())))
