# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import json
import time

from odoo.tests import HttpCase, TransactionCase, tagged

NOW = int(time.time())


def _payload(samples=(), events=(), status='OL CHRG'):
    return {
        'device': {'serial': 'TEST-1', 'manufacturer': 'APC', 'model': 'Back-UPS'},
        'vars': {'ups.status': status, 'battery.charge': '100', 'input.voltage': '229.0', 'ups.load': '17'},
        'samples': [{'ts': ts, 'm': {'battery.charge': str(charge), 'input.voltage': '229'}} for ts, charge in samples],
        'events': [{'id': i, 'ts': ts, 'kind': 'status_change', 'old': old, 'new': new}
                   for i, ts, old, new in events],
    }


@tagged('post_install', '-at_install')
class TestIngest(TransactionCase):

    def test_retry_is_idempotent(self):
        payload = _payload(samples=[(NOW - 120, 100), (NOW - 60, 99)],
                           events=[(1, NOW - 120, 'OL', 'OL CHRG')])
        first = self.env['ups.device']._ingest(payload)
        second = self.env['ups.device']._ingest(payload)
        self.assertEqual(first, {'samples': 2, 'events': 1})
        self.assertEqual(second, {'samples': 0, 'events': 0})
        device = self.env['ups.device'].search([('serial', '=', 'TEST-1')])
        self.assertRecordValues(device, [{'agent_state': 'online', 'status': 'OL CHRG', 'battery_charge': 100.0}])

    def test_outage_opens_and_closes(self):
        self.env['ups.device']._ingest(_payload(
            samples=[(NOW - 600, 100), (NOW - 540, 80), (NOW - 480, 60), (NOW - 420, 90)],
            events=[(1, NOW - 600, 'OL', 'OB DISCHRG'), (2, NOW - 420, 'OB DISCHRG', 'OL CHRG')],
        ))
        outage = self.env['ups.outage'].search([('device_id.serial', '=', 'TEST-1')])
        self.assertRecordValues(outage, [{'min_charge': 60.0, 'low_battery': False}])
        self.assertAlmostEqual(outage.duration, 3.0)

    def test_outage_stays_open_and_flags_low_battery(self):
        self.env['ups.device']._ingest(_payload(
            events=[(1, NOW - 60, 'OL', 'OB DISCHRG'), (2, NOW - 30, 'OB DISCHRG', 'OB DISCHRG LB')]))
        outage = self.env['ups.outage'].search([('device_id.serial', '=', 'TEST-1')])
        self.assertRecordValues(outage, [{'end': False, 'low_battery': True}])

    def test_cron_flags_silent_agent(self):
        self.env['ups.device']._ingest(_payload())
        device = self.env['ups.device'].search([('serial', '=', 'TEST-1')])
        device.last_seen = '2000-01-01 00:00:00'
        self.env['ups.device']._cron_check_agents()
        self.assertEqual(device.agent_state, 'offline')

    def test_missing_serial_is_refused(self):
        with self.assertRaises(ValueError):
            self.env['ups.device']._ingest({'device': {}})


@tagged('post_install', '-at_install')
class TestIngestRoute(HttpCase):

    def _post(self, token, payload):
        return self.url_open(
            '/ups_monitor/ingest', data=json.dumps(payload),
            headers={'Content-Type': 'application/json', 'X-Auth-Token': token})

    def test_token_gate(self):
        self.assertEqual(self._post('wrong', _payload()).status_code, 403)
        token = self.env['ir.config_parameter'].sudo().get_param('ups_monitor.token')
        self.assertTrue(token)
        response = self._post(token, _payload(samples=[(NOW - 60, 100)]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['samples'], 1)
