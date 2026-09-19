# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo.tests import tagged

from .common import FuelTelegramCase


@tagged('post_install', '-at_install')
class TestFuelBot(FuelTelegramCase):
    def test_start_offers_location_keyboard(self):
        self.send_text('/start')
        keyboard = self.sent()[-1]['reply_markup']['keyboard']
        self.assertTrue(keyboard[0][0]['request_location'])
        self.send_text('/aiuto')
        self.assertIn("/vicini", self.last_text())

    def station_cards(self):
        """(text, station callback, navigate url) of every station card sent since the last clear."""
        cards = []
        for payload in self.sent():
            rows = payload.get('reply_markup', {}).get('inline_keyboard', [])
            buttons = [button for row in rows for button in row]
            card = [b['callback_data'] for b in buttons if b.get('callback_data', '').startswith('st:')]
            if card and len(buttons) == 2:
                cards.append((payload['text'], card[0], buttons[0].get('url')))
        return cards

    def test_location_asks_fuel_mode_then_one_card_per_station(self):
        self.send_location(45.4642, 9.1900)
        self.assertIn('fuel:Benzina', self.last_buttons())
        self.assertIn('fuel:*', self.last_buttons())
        self.tap('fuel:Gasolio')
        self.assertEqual(self.chat().fuel_type, 'Gasolio')
        self.assertEqual(self.last_buttons(), ['mode:1', 'mode:0'], "self or served comes next")
        self.calls.clear()
        self.tap('mode:1')
        self.assertTrue(self.chat().mode_chosen)
        cards = self.station_cards()
        # Torino sits 125 km away and stays out; cheapest first, one message each
        self.assertEqual([card[1] for card in cards],
                         ['st:%s' % self.navigli.id, 'st:%s' % self.monza.id, 'st:%s' % self.duomo.id])
        self.assertTrue(cards[0][0].startswith("🥇 <b>1.749 €</b> · Gasolio Self"))
        self.assertIn("📍 MILANO · 2.", cards[0][0])
        self.assertIn("destination=45.45,9.17", cards[0][2])
        self.assertIn('near:dist', self.last_buttons(), "footer carries the toggles")
        self.assertIn('mode:0', self.last_buttons())

    def test_near_by_distance_and_vicini(self):
        self.send_location(45.4642, 9.1900)
        self.tap('fuel:Gasolio')
        self.tap('mode:1')
        self.calls.clear()
        self.tap('near:dist')
        self.assertEqual(self.station_cards()[0][1], 'st:%s' % self.duomo.id)
        self.assertNotIn("🥇", self.station_cards()[0][0], "no medals when sorted by distance")
        self.calls.clear()
        self.send_text('/vicini')
        self.assertEqual(self.station_cards()[0][1], 'st:%s' % self.navigli.id, "back to price order")

    def test_all_fuels_skips_mode_and_lists_by_distance(self):
        self.send_location(45.4642, 9.1900)
        self.calls.clear()
        self.tap('fuel:*')
        cards = self.station_cards()
        self.assertEqual(cards[0][1], 'st:%s' % self.duomo.id)
        self.assertIn("• Benzina Self <b>1.899 €</b>", cards[0][0])
        self.assertNotIn('mode:0', self.last_buttons())

    def test_text_search_by_city(self):
        self.send_text('monza')
        self.assertEqual([card[1] for card in self.station_cards()], ['st:%s' % self.monza.id])
        self.assertIn("⛽ <b>Q8 MONZA</b>", self.station_cards()[0][0])
        self.send_text('nowhere')
        self.assertIn("nowhere", self.last_text())
        self.assertIn('reply_markup', self.sent()[-1])

    def test_station_card_and_subscription_toggle(self):
        self.tap('st:%s' % self.duomo.id)
        self.assertEqual(self.sent('sendVenue')[0]['title'], "ENI DUOMO")
        gasolio = self.fuel(self.duomo, 'Gasolio')
        self.assertIn('sub:%s' % gasolio.id, self.last_buttons())
        self.assertNotIn('thrst:%s' % self.duomo.id, self.last_buttons())
        self.tap('sub:%s' % gasolio.id)
        sub = self.Sub.search([('chat_id', '=', self.chat().id), ('station_fuel_id', '=', gasolio.id)])
        self.assertTrue(sub.active)
        markup = self.sent('editMessageReplyMarkup')[-1]['reply_markup']['inline_keyboard']
        self.assertIn('url', markup[0][0], "first row navigates to the station")
        labels = {row[0].get('callback_data'): row[0]['text'] for row in markup}
        self.assertTrue(labels['sub:%s' % gasolio.id].startswith("✅"))
        self.assertTrue(labels['sub:%s' % self.fuel(self.duomo, 'Benzina').id].startswith("➕"))
        self.assertEqual(markup[-1][0]['callback_data'], 'thrst:%s' % self.duomo.id)
        self.tap('sub:%s' % gasolio.id)
        self.assertFalse(sub.active)

    def test_threshold_parser(self):
        gasolio = self.fuel(self.duomo, 'Gasolio')
        self.tap('sub:%s' % gasolio.id)
        sub = self.Sub.search([('station_fuel_id', '=', gasolio.id)])
        cases = [
            ('sopra 1,85', 1.85, 0.0), ('sotto 1.70', 0.0, 1.70), ('1.85-1.70', 1.85, 1.70),
            ('above 2', 2.0, 0.0), ('nessuna', 0.0, 0.0),
        ]
        for text, above, below in cases:
            self.send_text('/soglia')
            self.assertEqual(self.chat().state, 'threshold')
            self.send_text(text)
            with self.subTest(text=text):
                self.assertRecordValues(sub, [{'above_price': above, 'below_price': below}])
            self.assertEqual(self.chat().state, 'idle')
        self.send_text('/soglia')
        self.send_text('boh')
        self.assertEqual(self.chat().state, 'threshold', "bad input keeps waiting")
        self.assertIn("sopra 1.85", self.last_text())

    def test_notify_respects_thresholds(self):
        gasolio = self.fuel(self.duomo, 'Gasolio')
        benzina = self.fuel(self.duomo, 'Benzina')
        self.tap('sub:%s' % gasolio.id)
        self.tap('sub:%s' % benzina.id)
        subs = self.Sub.search([('chat_id', '=', self.chat().id)])
        subs.filtered(lambda s: s.station_fuel_id == gasolio).write({'above_price': 1.85, 'below_price': 1.70})
        Price = self.env['fuel.price']

        def change(fuel, price, mimit_price_id):
            row = Price.create({'station_fuel_id': fuel.id, 'price': price, 'previous_price': fuel.current_price,
                                'date_communicated': '2026-09-19 06:00:00', 'mimit_price_id': mimit_price_id})
            fuel.write({'current_price': price})
            self.calls.clear()
            self.env['fuel.station.fuel']._notify_followers(row)
            return self.sent()

        self.assertFalse(change(gasolio, 1.80, 101), "inside the range: silent")
        alerts = change(gasolio, 1.69, 102)
        self.assertEqual(len(alerts), 1, "below the range: one alert")
        self.assertIn("1.800 → <b>1.690</b> (-0.110)", alerts[0]['text'])
        self.assertEqual(alerts[0]['chat_id'], 4242)
        self.assertEqual(alerts[0]['reply_markup']['inline_keyboard'][0][0]['callback_data'], 'st:%s' % self.duomo.id)
        self.assertTrue(change(gasolio, 1.90, 103), "above the range: alert")
        self.assertTrue(change(benzina, 1.90, 104), "no thresholds: every change")

    def test_lista_prezzi_delete_stop(self):
        gasolio = self.fuel(self.duomo, 'Gasolio')
        self.tap('sub:%s' % gasolio.id)
        sub = self.Sub.search([('station_fuel_id', '=', gasolio.id)])
        self.send_text('/lista')
        self.assertIn("ENI DUOMO", self.last_text())
        self.assertEqual(self.last_buttons(), ['thr:%s' % sub.id, 'del:%s' % sub.id, 'st:%s' % self.duomo.id])
        self.send_text('/prezzi')
        self.assertIn("<b>1.799</b>", self.last_text())
        self.tap('del:%s' % sub.id)
        self.assertFalse(sub.active)
        self.tap('sub:%s' % gasolio.id)
        self.assertTrue(sub.active, "re-follow revives the same row")
        self.send_text('/stop')
        self.assertFalse(sub.active)
        self.assertFalse(self.chat().active)
        self.send_text('/start')
        self.assertTrue(self.chat().active, "any message revives the chat")
        self.assertFalse(sub.active, "subscriptions stay removed")
