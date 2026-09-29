# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import re
from datetime import timezone
from html import escape

from odoo import _, fields, models
from odoo.tools import formatLang

from .telegram_bot import STATION_TZ

NUMBER = r'(\d+(?:[.,]\d+)?)'
RE_RANGE = re.compile(r'^\s*' + NUMBER + r'\s*[-–]\s*' + NUMBER + r'\s*$')
RE_ABOVE = re.compile(r'^\s*(?:sopra|above|>)\s*' + NUMBER + r'\s*$', re.I)
RE_BELOW = re.compile(r'^\s*(?:sotto|below|<)\s*' + NUMBER + r'\s*$', re.I)
RESET_WORDS = ('nessuna', 'none', 'no', '0', 'reset')
ALL_FUELS = '*'
# fuel.type caches the families MIMIT publishes; they lead the keyboard and the commercial
# blends (Blue Diesel, HVOlution, ...) follow by how many stations sell them
FALLBACK_FUELS = ('Benzina', 'Gasolio', 'Metano', 'GPL', 'GNL', 'L-GNC')
# a monospaced line wider than this wraps on a phone
NAME_WIDTH = 22
BUTTONS_PER_ROW = 5
QUOTE_FROM = 6


class TelegramHandlerFuel(models.AbstractModel):
    """Conversation of the fuel price bot (telegram.bot.kind = 'fuel')."""
    _name = 'telegram.handler.fuel'
    _inherit = 'telegram.handler'
    _description = "Telegram Handler: Fuel Prices"

    def _commands(self):
        own = dict(
            vicini=_("Prices around your last location"),
            carburante=_("Change the fuel you are looking for"),
            lista=_("Manage your subscriptions"),
            prezzi=_("Current prices of your subscriptions"),
            storico=_("Price history of the last station you opened"),
            soglia=_("Set alert thresholds"),
            stop=_("Remove every subscription"),
            aiuto=_("Help"),
        )
        return super()._commands() + list(own.items())

    # ------------------------------------------------------------------
    # formatting
    # ------------------------------------------------------------------
    def _fmt_price(self, value):
        """Price in the reader's locale: 1,749 in Italian, 1.749 in English."""
        return formatLang(self.env, value, digits=3)

    def _short(self, text, width=NAME_WIDTH):
        text = text or ""
        return text if len(text) <= width else text[:width - 1] + "…"

    def _age(self, value):
        """Compact age of a price: 40m, 6h, 3d."""
        if not value:
            return ""
        seconds = (fields.Datetime.now() - value).total_seconds()
        if seconds < 3600:
            return _("%dm") % max(int(seconds // 60), 1)
        if seconds < 172800:
            return _("%dh") % int(seconds // 3600)
        return _("%dd") % int(seconds // 86400)

    def _stamp(self, value):
        """Day, month, year and time of a communication, in Italian station time."""
        if not value:
            return ""
        return fields.Datetime.context_timestamp(
            self.with_context(tz=STATION_TZ), value).strftime('%d/%m/%Y %H:%M')

    def _when(self, value):
        """Relative time the Telegram client renders in the reader's language."""
        if not value:
            return ""
        stamp = int(value.replace(tzinfo=timezone.utc).timestamp())
        return '<tg-time unix="%s" format="r">%s</tg-time>' % (stamp, self._age(value))

    def _trend(self, fuel):
        """Arrow and the price it replaced, or a dash while the first price holds."""
        if not fuel.previous_price:
            return "-"
        arrow = "▲" if fuel.current_price > fuel.previous_price else "▼"
        return "%s %s" % (arrow, self._fmt_price(fuel.previous_price))

    def _block(self, lines):
        """Monospaced block: columns stay aligned, no inline formatting inside."""
        return "<pre>%s</pre>" % escape("\n".join(lines))

    def _number_keyboard(self, callbacks):
        buttons = [{'text': str(index), 'callback_data': data} for index, data in enumerate(callbacks, 1)]
        return [buttons[i:i + BUTTONS_PER_ROW] for i in range(0, len(buttons), BUTTONS_PER_ROW)]

    def _say_or_edit(self, chat, text, keyboard=None, message=None):
        """Rewrite the message the button belongs to, or send a new one."""
        if not message:
            return chat._say(text, keyboard=keyboard)
        return chat.bot_id._call('editMessageText', chat_id=chat.chat_id, message_id=message['message_id'],
                                 text=text, parse_mode='HTML',
                                 link_preview_options={'is_disabled': True},
                                 reply_markup={'inline_keyboard': keyboard or []})

    # ------------------------------------------------------------------
    # routing hooks
    # ------------------------------------------------------------------
    def _on_free_text(self, chat, text):
        if chat.state == 'threshold':
            return self._set_threshold(chat, text)
        return self._search_stations(chat, text)

    def _on_location(self, chat, location):
        chat.write({'last_latitude': location['latitude'], 'last_longitude': location['longitude']})
        if not chat.fuel_type:
            return self._ask_fuel(chat)
        if chat.fuel_type != ALL_FUELS and not chat.mode_chosen:
            return self._ask_mode(chat)
        return self._send_nearest(chat)

    # ------------------------------------------------------------------
    # callbacks
    # ------------------------------------------------------------------
    def _cb_st(self, chat, arg, message):
        # only a card opened from a list takes its place; an alert keeps its message
        station_id, _sep, origin = arg.partition(':')
        self._show_station(chat, int(station_id), message=message if origin else None, origin=origin)

    def _cb_back(self, chat, arg, message):
        if arg == 'list':
            return self._cmd_lista(chat, message=message)
        if arg == 'search':
            return self._search_stations(chat, chat.last_search or '', message=message)
        self._send_nearest(chat, message=message)

    def _cb_subd(self, chat, arg, message):
        self._show_subscription(chat, int(arg), message=message)

    def _cb_sub(self, chat, arg, message):
        self._toggle_subscription(chat, int(arg), message)

    def _cb_thr(self, chat, arg, message):
        self._ask_threshold(chat, int(arg))

    def _cb_thrst(self, chat, arg, message):
        self._cmd_soglia(chat, station_id=int(arg))

    def _cb_del(self, chat, arg, message):
        self._remove_subscription(chat, int(arg), message=message)

    def _cb_fuel(self, chat, arg, message):
        if not arg:
            return self._ask_fuel(chat)
        chat.write({'fuel_type': arg})
        if arg != ALL_FUELS:
            return self._ask_mode(chat)
        self._send_nearest_or_ask_location(chat)

    def _cb_mode(self, chat, arg, message):
        chat.write({'is_self': arg == '1', 'mode_chosen': True})
        self._send_nearest_or_ask_location(chat)

    def _cb_near(self, chat, arg, message):
        chat.write({'last_order': arg})
        self._send_nearest(chat, message=message)

    def _cb_hist(self, chat, arg, message):
        self._send_history(chat, int(arg))

    def _send_nearest_or_ask_location(self, chat):
        if chat.last_latitude:
            self._send_nearest(chat)
        else:
            chat._say(_("Now send me your location."), reply_keyboard=self._location_keyboard())

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def _location_keyboard(self):
        return {'keyboard': [[{'text': _("📍 Send my location"), 'request_location': True}]],
                'resize_keyboard': True}

    def _cmd_start(self, chat):
        chat._say(_("Hi! Send me your location to see fuel prices around you, "
                    "or type a town name to search a station.\n"
                    "Open a station to follow one or more fuels: I will message you at every "
                    "price change, or only outside the thresholds you set.\n\n/aiuto for the commands."),
                  reply_keyboard=self._location_keyboard())

    def _cmd_aiuto(self, chat):
        self._cmd_help(chat)

    def _cmd_vicini(self, chat):
        if not chat.last_latitude:
            return chat._say(_("Send me your location first."), reply_keyboard=self._location_keyboard())
        if not chat.fuel_type:
            return self._ask_fuel(chat)
        self._send_nearest(chat)

    def _cmd_carburante(self, chat):
        self._ask_fuel(chat)

    def _cmd_lista(self, chat, message=None):
        subs = chat.subscription_ids
        if not subs:
            return self._say_or_edit(
                chat, _("No subscriptions yet. Send your location or a town name to find a station."),
                message=message)
        header = _("📋 Your subscriptions · %s") % len(subs)
        blocks = [escape(header)]
        for index, sub in enumerate(subs, 1):
            blocks.append(self._subscription_lines(index, sub))
        keyboard = self._number_keyboard(['subd:%s' % sub.id for sub in subs])
        self._say_or_edit(chat, "\n\n".join(blocks), keyboard=keyboard, message=message)

    def _subscription_lines(self, index, sub):
        """One readable block per subscription: station, fuel, price, when, alert rule."""
        fuel = sub.station_fuel_id
        town = ", ".join(p for p in (fuel.station_id.city, fuel.station_id.province) if p)
        lines = ["<b>%s · %s</b>" % (index, escape(fuel.station_id.name))]
        if town:
            lines.append("📍 %s" % escape(town))
        lines.append("%s · <b>%s €</b>%s" % (escape(self._fuel_label(fuel)),
                                             self._fmt_price(fuel.current_price), self._move(fuel)))
        lines.append("🕒 %s" % escape(self._stamp(fuel.current_date)))
        lines.append("🔔 %s" % escape(sub._threshold_label()))
        return "\n".join(lines)

    def _move(self, fuel):
        """' ▼ 1,849' after the price, empty while the first price holds."""
        if not fuel.previous_price:
            return ""
        arrow = "▲" if fuel.current_price > fuel.previous_price else "▼"
        return " %s %s" % (arrow, self._fmt_price(fuel.previous_price))

    def _cmd_prezzi(self, chat):
        subs = chat.subscription_ids
        if not subs:
            return chat._say(_("No subscriptions yet. Send your location or a town name to find a station."))
        header = _("💶 Prices you follow · %s") % len(subs)
        blocks = [escape(header)]
        for sub in subs:
            fuel = sub.station_fuel_id
            blocks.append("<b>%s €</b>%s · %s\n%s · 🕒 %s" % (
                self._fmt_price(fuel.current_price), self._move(fuel), escape(self._fuel_label(fuel)),
                escape(fuel.station_id.name), escape(self._stamp(fuel.current_date))))
        chat._say("\n\n".join(blocks))

    def _cmd_storico(self, chat):
        if not chat.last_station_id:
            return chat._say(_("Open a station first: send your location or a town name."))
        self._send_history(chat, chat.last_station_id.id)

    def _send_history(self, chat, station_id, limit=12):
        station = self.env['fuel.station'].browse(station_id).exists()
        if not station:
            return chat._say(_("Station not found."))
        chat.write({'last_station_id': station.id})
        bot = chat.bot_id
        rows = self.env['fuel.price'].search([('station_id', '=', station.id)], limit=limit)
        if not rows:
            return chat._say(_("No price change recorded for %s yet.") % escape(station.name))
        lines = []
        for row in rows:
            label = self._short(self._fuel_label(row.station_fuel_id), 16)
            if row.previous_price:
                lines.append("%s  %s  %s → %s" % (bot._fmt_station_dt(row.date_communicated), label,
                                                  self._fmt_price(row.previous_price),
                                                  self._fmt_price(row.price)))
            else:
                lines.append("%s  %s  %s %s" % (bot._fmt_station_dt(row.date_communicated), label,
                                                self._fmt_price(row.price), _("first price")))
        header = _("📈 %s · last changes") % self._short(station.name, 26)
        body = self._block(lines)
        if len(lines) > QUOTE_FROM:
            body = "<blockquote expandable>%s</blockquote>" % body
        chat._say("%s\n%s" % (escape(header), body), keyboard=self._station_buttons(chat, station))

    def _cmd_soglia(self, chat, station_id=None):
        subs = chat.subscription_ids
        if station_id:
            subs = subs.filtered(lambda s: s.station_id.id == station_id)
        if not subs:
            return chat._say(_("Follow a fuel first: open a station and tap the fuel."))
        if len(subs) == 1:
            return self._ask_threshold(chat, subs.id)
        keyboard = [[{'text': "%s %s" % (self._short(s.station_id.name, 16), self._fuel_label(s.station_fuel_id)),
                      'callback_data': 'thr:%s' % s.id}] for s in subs]
        chat._say(_("Which subscription?"), keyboard=keyboard)

    def _cmd_stop(self, chat):
        chat.subscription_ids.write({'active': False})
        chat.write({'pending_subscription_id': False})
        super()._cmd_stop(chat)

    # ------------------------------------------------------------------
    # search and nearest
    # ------------------------------------------------------------------
    def _fuel_choices(self):
        """Every fuel on sale, the everyday ones first, then by how many stations sell it."""
        groups = self.env['fuel.station.fuel']._read_group(
            [('current_price', '>', 0)], groupby=['fuel_type'], aggregates=['__count'],
            order='__count desc')
        available = [fuel_type for fuel_type, _count in groups]
        families = self.env['fuel.type'].search([]).mapped('name') or list(FALLBACK_FUELS)
        pinned = [fuel for fuel in families if fuel in available]
        return pinned + [fuel for fuel in available if fuel not in pinned]

    def _ask_fuel(self, chat):
        # two per row: some blends carry long names
        buttons = [{'text': fuel_type, 'callback_data': 'fuel:%s' % fuel_type}
                   for fuel_type in self._fuel_choices()]
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        keyboard.append([{'text': _("All fuels"), 'callback_data': 'fuel:' + ALL_FUELS}])
        chat._say(_("Which fuel are you looking for?"), keyboard=keyboard)

    def _ask_mode(self, chat):
        self_label = _("Self service")
        served_label = _("Served")
        chat._say(_("Self service or served?"), keyboard=[[
            {'text': "🤳 " + self_label, 'callback_data': 'mode:1'},
            {'text': "🧑‍🔧 " + served_label, 'callback_data': 'mode:0'},
        ]])

    def _limit(self):
        return int(self.env['ir.config_parameter'].sudo().get_param('fuel_telegram.nearest_limit', 10) or 10)

    def _station_buttons(self, chat, station):
        navigate = _("🧭 Navigate")
        card = _("⛽ Station")
        return [[{'text': navigate, 'url': chat.bot_id._maps_link(station)},
                 {'text': card, 'callback_data': 'st:%s' % station.id}]]

    def _send_nearest(self, chat, message=None):
        lat, lng = chat.last_latitude, chat.last_longitude
        all_fuels = chat.fuel_type == ALL_FUELS
        order = chat.last_order or 'price'
        if all_fuels:
            cards = [(station, km, None) for km, station in self.env['fuel.station']._nearest(lat, lng, self._limit())]
        else:
            ranked = self.env['fuel.station.fuel']._nearest(lat, lng, chat.fuel_type, chat.is_self, self._limit())
            if order == 'dist':
                ranked.sort(key=lambda pair: pair[0])
            else:
                ranked.sort(key=lambda pair: (pair[1].current_price, pair[0]))
            cards = [(fuel.station_id, km, fuel) for km, fuel in ranked]
        if not cards:
            change_fuel = _("Change fuel")
            return self._say_or_edit(
                chat, _("No station with %s within 100 km of this point.") % escape(chat.fuel_type or ""),
                keyboard=[[{'text': change_fuel, 'callback_data': 'fuel:'}]], message=message)
        # labels first: a parenthesis opened right after a _() call confuses the term extractor
        by_distance = order == 'dist' or all_fuels
        fuel_label = _("All fuels") if all_fuels else chat.fuel_type
        order_label = _("by distance") if by_distance else _("by price")
        header = _("⛽ %(fuel)s %(mode)s · %(order)s · %(count)s stations",
                   fuel=fuel_label, mode="" if all_fuels else self._mode_label(chat),
                   order=order_label, count=len(cards))
        lines = []
        for index, (station, km, fuel) in enumerate(cards, 1):
            if fuel is not None:
                lines.append("%2d  %7s €  %-9s %s" % (index, self._fmt_price(fuel.current_price),
                                                     self._trend(fuel), self._age(fuel.current_date)))
                lines.append("    %s · %s" % (self._short(station.name, 18), self._km(km)))
            else:
                lines.append("%2d  %s · %s" % (index, self._short(station.name, 18), self._km(km)))
                prices = "  ".join("%s %s" % (self._short(row.fuel_type, 10), self._fmt_price(row.current_price))
                                   for row in station.fuel_ids.filtered('current_price'))
                lines.append("    %s" % prices)
        keyboard = self._number_keyboard(['st:%s:near' % station.id for station, _km, _fuel in cards])
        toggle_label = _("💶 By price") if by_distance else _("📏 By distance")
        mode_label = _("Served") if chat.is_self else _("Self service")
        fuel_button = _("⛽ Fuel")
        row = [{'text': fuel_button, 'callback_data': 'fuel:'}]
        if not all_fuels:
            row.insert(0, {'text': mode_label, 'callback_data': 'mode:0' if chat.is_self else 'mode:1'})
            row.insert(0, {'text': toggle_label, 'callback_data': 'near:price' if by_distance else 'near:dist'})
        keyboard.append(row)
        self._say_or_edit(chat, "%s\n%s" % (escape(header), self._block(lines)),
                          keyboard=keyboard, message=message)

    def _km(self, km):
        return _("%.1f km") % km

    def _search_stations(self, chat, text, message=None):
        # never name this _search: it would shadow the ORM method
        stations = self.env['fuel.station'].search(
            ['&', ('fuel_ids.current_price', '>', 0), '|', ('city', 'ilike', text), ('name', 'ilike', text)],
            limit=10, order='city, name')
        if not stations:
            return chat._say(_("No station found for \"%s\". Try a town name or send your location.") % escape(text),
                             reply_keyboard=self._location_keyboard())
        chat.write({'last_search': text})
        lines = []
        for index, station in enumerate(stations, 1):
            lines.append("%2d  %s · %s" % (index, self._short(station.name, 18), self._short(station.city or "", 12)))
            prices = "  ".join("%s %s" % (self._short(row.fuel_type, 10), self._fmt_price(row.current_price))
                               for row in station.fuel_ids.filtered('current_price'))
            lines.append("    %s" % prices)
        header = _("🔎 %(text)s · %(count)s stations", text=self._short(text, 20), count=len(stations))
        keyboard = self._number_keyboard(['st:%s:search' % station.id for station in stations])
        self._say_or_edit(chat, "%s\n%s" % (escape(header), self._block(lines)),
                          keyboard=keyboard, message=message)

    # ------------------------------------------------------------------
    # station card and subscriptions
    # ------------------------------------------------------------------
    def _fuel_label(self, fuel):
        return "%s %s" % (fuel.fuel_type, _("Self") if fuel.is_self else _("Served"))

    def _mode_label(self, chat):
        return _("Self") if chat.is_self else _("Served")

    def _station_keyboard(self, chat, station, origin=''):
        followed = set(chat.subscription_ids.mapped('station_fuel_id').ids)
        navigate = _("🧭 Navigate")
        keyboard = [[{'text': navigate, 'url': chat.bot_id._maps_link(station)}]]
        keyboard += [[{'text': "%s %s" % ("✅" if fuel.id in followed else "➕", self._fuel_label(fuel)),
                       'callback_data': 'sub:%s' % fuel.id}]
                     for fuel in station.fuel_ids.filtered('current_price')]
        history = _("📈 History")
        row = [{'text': history, 'callback_data': 'hist:%s' % station.id}]
        if followed & set(station.fuel_ids.ids):
            row.append({'text': _("⚙️ Thresholds"), 'callback_data': 'thrst:%s' % station.id})
        keyboard.append(row)
        if origin:
            back = _("🔙 List")
            keyboard.append([{'text': back, 'callback_data': 'back:%s' % origin}])
        return keyboard

    def _station_text(self, chat, station):
        address = ", ".join(p for p in (station.street, station.city, station.province) if p) or station.address or ""
        lines = ["⛽ <b>%s</b> · %s" % (escape(station.name), escape(station.brand or "")),
                 "📍 %s" % escape(address)]
        lines.append("")
        for fuel in station.fuel_ids.filtered('current_price'):
            lines.append("%s · <b>%s €</b>%s\n🕒 %s" % (
                escape(self._fuel_label(fuel)), self._fmt_price(fuel.current_price), self._move(fuel),
                escape(self._stamp(fuel.current_date))))
        lines.append("")
        lines.append(escape(_("Tap a fuel to follow it, tap again to stop.")))
        return "\n".join(lines)

    def _show_station(self, chat, station_id, message=None, origin=''):
        station = self.env['fuel.station'].browse(station_id).exists()
        if not station:
            return chat._say(_("Station not found."))
        chat.write({'last_station_id': station.id})
        self._say_or_edit(chat, self._station_text(chat, station),
                          keyboard=self._station_keyboard(chat, station, origin=origin), message=message)

    def _show_subscription(self, chat, sub_id, message=None):
        sub = chat.subscription_ids.filtered(lambda s: s.id == sub_id)
        if not sub:
            return self._cmd_lista(chat, message=message)
        fuel = sub.station_fuel_id
        station = fuel.station_id
        chat.write({'last_station_id': station.id})
        previous = self._fmt_price(fuel.previous_price) if fuel.previous_price else _("no change yet")
        lines = ["⛽ <b>%s</b> · %s" % (escape(station.name), escape(station.brand or "")),
                 "📍 %s" % escape(", ".join(p for p in (station.street, station.city) if p) or station.address or ""),
                 "",
                 "%s · <b>%s €</b>" % (escape(self._fuel_label(fuel)), self._fmt_price(fuel.current_price)),
                 "%s %s · %s %s / %s" % (escape(_("before")), escape(previous), escape(_("min / max")),
                                         self._fmt_price(fuel.min_price), self._fmt_price(fuel.max_price)),
                 "🕒 %s · %s" % (escape(self._stamp(fuel.current_date)), self._when(fuel.current_date)),
                 "🔔 %s" % escape(sub._threshold_label())]
        keyboard = [
            [{'text': _("⚙️ Thresholds"), 'callback_data': 'thr:%s' % sub.id},
             {'text': _("🗑 Remove"), 'callback_data': 'del:%s' % sub.id}],
            [{'text': _("📈 History"), 'callback_data': 'hist:%s' % station.id},
             {'text': _("🧭 Navigate"), 'url': chat.bot_id._maps_link(station)}],
            [{'text': _("⛽ Station"), 'callback_data': 'st:%s' % station.id},
             {'text': _("🔙 List"), 'callback_data': 'back:list'}],
        ]
        self._say_or_edit(chat, "\n".join(lines), keyboard=keyboard, message=message)

    def _toggle_subscription(self, chat, station_fuel_id, message):
        fuel = self.env['fuel.station.fuel'].browse(station_fuel_id).exists()
        if not fuel:
            return chat._say(_("Price list not found."))
        Sub = self.env['fuel.telegram.subscription'].with_context(active_test=False)
        sub = Sub.search([('chat_id', '=', chat.id), ('station_fuel_id', '=', fuel.id)], limit=1)
        if sub and sub.active:
            sub.write({'active': False})
            chat._say(_("Unfollowed %s.") % escape(fuel.display_name))
        else:
            if sub:
                sub.write({'active': True, 'above_price': 0, 'below_price': 0})
            else:
                Sub.create({'chat_id': chat.id, 'station_fuel_id': fuel.id})
            chat._say(_("Following %s: you get a message at every price change. "
                        "Set thresholds with /soglia.") % escape(fuel.display_name))
        chat.invalidate_recordset(['subscription_ids'])
        chat.bot_id._call('editMessageReplyMarkup', chat_id=chat.chat_id, message_id=message['message_id'],
                          reply_markup={'inline_keyboard': self._station_keyboard(chat, fuel.station_id)})

    def _remove_subscription(self, chat, sub_id, message=None):
        sub = chat.subscription_ids.filtered(lambda s: s.id == sub_id)
        if sub:
            name = sub.station_fuel_id.display_name
            sub.write({'active': False})
            chat._say(_("Unfollowed %s.") % escape(name))
        chat.invalidate_recordset(['subscription_ids'])
        self._cmd_lista(chat, message=message)

    def _ask_threshold(self, chat, sub_id):
        sub = self.env['fuel.telegram.subscription'].browse(sub_id).exists()
        if not sub or sub.chat_id != chat:
            return chat._say(_("Subscription not found."))
        chat.write({'state': 'threshold', 'pending_subscription_id': sub.id})
        chat._say(_("%(name)s, now %(price)s, alert %(rule)s.\n"
                    "Send the new rule:\n"
                    "<code>sopra 1.85</code> alert above 1.85\n"
                    "<code>sotto 1.70</code> alert below 1.70\n"
                    "<code>1.70-1.85</code> alert outside the range\n"
                    "<code>nessuna</code> alert at every change",
                    name=escape(sub.station_fuel_id.display_name),
                    price=self._fmt_price(sub.current_price), rule=escape(sub._threshold_label())))

    def _set_threshold(self, chat, text):
        sub = chat.pending_subscription_id
        if not sub or not sub.active:
            chat._reset_state()
            return chat._say(_("Subscription not found."))
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
            return chat._say(_("I did not understand. Examples: <code>sopra 1.85</code>, "
                               "<code>sotto 1.70</code>, <code>1.70-1.85</code>, <code>nessuna</code>."))
        sub.write(vals)
        chat._reset_state()
        chat._say(_("%(name)s: alert %(rule)s.", name=escape(sub.station_fuel_id.display_name),
                    rule=escape(sub._threshold_label())))
