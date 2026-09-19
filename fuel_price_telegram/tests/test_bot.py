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

    def test_location_asks_fuel_then_lists_by_price(self):
        self.send_location(45.4642, 9.1900)
        self.assertIn('fuel:Benzina', self.last_buttons())
        self.assertIn('fuel:*', self.last_buttons())
        self.tap('fuel:Gasolio')
        self.assertEqual(self.chat().fuel_type, 'Gasolio')
        text = self.last_text()
        # Torino sits 125 km away and stays out; Milan and Monza stations come cheapest first
        self.assertNotIn("TORINO", text)
        self.assertLess(text.index("1.749"), text.index("1.769"))
        self.assertLess(text.index("1.769"), text.index("1.799"))
        self.assertIn("destination=45.45,9.17", text)
        buttons = self.last_buttons()
        self.assertEqual(buttons[:3], ['st:%s' % self.navigli.id, 'st:%s' % self.monza.id, 'st:%s' % self.duomo.id])
        self.assertIn('near:dist', buttons)

    def test_near_by_distance_and_vicini(self):
        self.send_location(45.4642, 9.1900)
        self.tap('fuel:Gasolio')
        self.tap('near:dist')
        self.assertEqual(self.last_buttons()[0], 'st:%s' % self.duomo.id)
        self.send_text('/vicini')
        self.assertEqual(self.last_buttons()[0], 'st:%s' % self.navigli.id, "back to price order")

    def test_all_fuels_lists_stations_by_distance(self):
        self.send_location(45.4642, 9.1900)
        self.tap('fuel:*')
        text = self.last_text()
        self.assertLess(text.index("ENI DUOMO"), text.index("IP NAVIGLI"))
        self.assertIn("Benzina Self <b>1.899</b>", text)

    def test_text_search_by_city(self):
        self.send_text('monza')
        self.assertEqual(self.last_buttons(), ['st:%s' % self.monza.id])
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
        labels = {row[0]['callback_data']: row[0]['text'] for row in markup}
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
