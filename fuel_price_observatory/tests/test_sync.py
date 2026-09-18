# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import copy
import json
from pathlib import Path
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.fuel_price_observatory.models.fuel_station import FuelStation
from odoo.addons.fuel_price_observatory.models.fuel_station_fuel import FuelStationFuel

DATA = Path(__file__).parent / 'data'


@tagged('post_install', '-at_install')
class TestSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dump = json.loads((DATA / 'servicearea_sample.json').read_text())['results']
        cls.csv_text = (DATA / 'anagrafica_sample.csv').read_text()
        cls.Station = cls.env['fuel.station']
        cls.Fuel = cls.env['fuel.station.fuel']
        cls.Price = cls.env['fuel.price']
        cls.user = cls.env['res.users'].create({
            'name': "Follower", 'login': 'follower', 'email': 'follower@example.com',
            'notification_type': 'email',
        })

    def _sync(self, dump):
        with patch.object(FuelStationFuel, '_fetch_api', return_value=dump):
            self.Fuel._cron_sync_prices()

    def _sync_csv(self, text):
        with patch.object(FuelStation, '_fetch_registry_csv', return_value=text):
            self.Station._cron_sync_stations()

    def _fuel(self, mimit_id, fuel_type, is_self):
        return self.Fuel.search([('station_id.mimit_id', '=', mimit_id),
                                 ('fuel_type', '=', fuel_type), ('is_self', '=', is_self)])

    def test_first_sync_creates_everything(self):
        self._sync(self.dump)
        self.assertEqual(self.Station.search_count([('mimit_id', 'in', [1001, 1002])]), 2)
        self.assertEqual(len(self.Fuel.search([('station_id.mimit_id', 'in', [1001, 1002])])), 5)
        fuel = self._fuel(1001, 'Gasolio', True)
        self.assertRecordValues(fuel, [{
            'current_price': 1.799, 'mimit_price_id': 5003, 'fuel_code': 2,
            'min_price': 1.799, 'max_price': 1.799,
        }])
        self.assertEqual(fuel.current_date.isoformat(), '2026-09-18T06:00:00')
        self.assertRecordValues(fuel.price_ids, [{'price': 1.799, 'previous_price': 0.0}])
        self.assertEqual(fuel.display_name, "ENI VIA ROMA - Gasolio Self")

    def test_resync_same_ids_is_noop(self):
        self._sync(self.dump)
        before = self.Price.search_count([])
        self._sync(self.dump)
        self.assertEqual(self.Price.search_count([]), before)

    def test_new_id_same_price_updates_date_only(self):
        self._sync(self.dump)
        dump = copy.deepcopy(self.dump)
        dump[0]['insertDate'] = '2026-09-19T08:00:00+02:00'
        for fuel in dump[0]['fuels']:
            fuel['id'] += 100
        self._sync(dump)
        fuel = self._fuel(1001, 'Gasolio', True)
        self.assertRecordValues(fuel, [{'current_price': 1.799, 'mimit_price_id': 5103}])
        self.assertEqual(fuel.current_date.isoformat(), '2026-09-19T06:00:00')
        self.assertEqual(len(fuel.price_ids), 1)

    def test_price_change_appends_history(self):
        self._sync(self.dump)
        for day, price in (('19', 1.749), ('20', 1.849), ('21', 1.749)):
            dump = copy.deepcopy(self.dump)
            dump[0]['insertDate'] = f'2026-09-{day}T08:00:00+02:00'
            dump[0]['fuels'][2].update(id=5003 + int(day), price=price)
            self._sync(dump)
        fuel = self._fuel(1001, 'Gasolio', True)
        self.assertEqual(len(fuel.price_ids), 4)
        self.assertRecordValues(fuel.price_ids[:2], [
            {'price': 1.749, 'previous_price': 1.849},
            {'price': 1.849, 'previous_price': 1.749},
        ])
        self.assertRecordValues(fuel, [{'current_price': 1.749, 'min_price': 1.749, 'max_price': 1.849}])
        # tie on the minimum: the most recent communication wins
        self.assertEqual(fuel.min_date.isoformat(), '2026-09-21T06:00:00')
        self.assertEqual(fuel.max_date.isoformat(), '2026-09-20T06:00:00')

    def test_alert_only_for_followers(self):
        self._sync(self.dump)
        followed = self._fuel(1001, 'Gasolio', True)
        other = self._fuel(1001, 'Benzina', True)
        followed.message_subscribe(partner_ids=self.user.partner_id.ids)
        dump = copy.deepcopy(self.dump)
        dump[0]['insertDate'] = '2026-09-19T08:00:00+02:00'
        dump[0]['fuels'][0].update(id=5101, price=1.999)
        dump[0]['fuels'][2].update(id=5103, price=1.699)
        self._sync(dump)
        subtype = self.env.ref('fuel_price_observatory.mt_price_change')
        alerts = self.env['mail.message'].search([
            ('model', '=', 'fuel.station.fuel'), ('subtype_id', '=', subtype.id)])
        self.assertEqual(alerts.mapped('res_id'), followed.ids)
        self.assertIn("1.799", alerts.body)
        self.assertIn("1.699", alerts.body)
        self.assertFalse(other.message_ids.filtered(lambda m: m.subtype_id == subtype))
        self.assertTrue(alerts.notification_ids.filtered(
            lambda n: n.res_partner_id == self.user.partner_id and n.notification_type == 'email'))

    def test_csv_enriches_station_and_deactivates_missing(self):
        self._sync(self.dump)
        self._sync_csv(self.csv_text)
        eni = self.Station.search([('mimit_id', '=', 1001)])
        self.assertRecordValues(eni, [{
            'name': 'ENI VIA ROMA', 'manager': 'ENI SPA', 'station_type': 'Stradale', 'city': 'MILANO', 'province': 'MI',
            'street': 'VIA ROMA 1', 'active': True,
        }])
        self.assertTrue(self.Station.search([('mimit_id', '=', 1004), ('name', '=', 'Q8 NUOVO')]))
        self.assertFalse(self.Station.search([('mimit_id', '=', 1003)]), "malformed row skipped")
        ip = self.Station.with_context(active_test=False).search([('mimit_id', '=', 1002)])
        self.assertFalse(ip.active, "station missing from the registry gets archived")
        self.assertEqual(self._fuel(1001, 'Gasolio', True).city, 'MILANO', "related stored fields follow")
