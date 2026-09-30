# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import json
from datetime import datetime, timedelta, timezone

from odoo import api, fields, models

# columns of one series row sent to the browser, in this order (after the bucket time)
SERIES_COLUMNS = """
    avg(input_voltage), min(input_voltage_min), max(input_voltage_max),
    avg(battery_charge), min(battery_charge_min),
    avg(ups_load), max(ups_load_max),
    avg(battery_runtime), min(battery_runtime_min),
    avg(battery_voltage), min(battery_voltage_min)
"""


def _ms(value):
    """Naive UTC datetime -> epoch milliseconds."""
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000) if value else None


def _from_ms(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).replace(tzinfo=None)


class UpsDashboard(models.AbstractModel):
    _name = 'ups.dashboard'
    _description = "UPS Dashboard"

    @api.model
    def get_data(self, device_id=None, date_from=None, date_to=None):
        """Everything the dashboard draws, for one UPS and one period.

        date_from / date_to are epoch milliseconds; date_from=None means "since the first sample".
        The bucket size follows the period so a chart never carries more than about 3000 points.
        """
        Sample = self.env['ups.sample']
        Sample.check_access('read')
        devices = self.env['ups.device'].search([])
        device = devices.filtered(lambda d: d.id == device_id) or devices[:1]
        if not device:
            return {'devices': []}

        now = fields.Datetime.now()
        end = _from_ms(date_to) if date_to else now
        first = Sample.search([('device_id', '=', device.id)], order='timestamp', limit=1).timestamp
        start = _from_ms(date_from) if date_from else (first or end - timedelta(days=1))
        span = max((end - start).total_seconds(), 60)
        bucket = 'minute' if span <= 2 * 86400 else 'hour' if span <= 120 * 86400 else 'day'

        # plain SQL: _read_group has no minute granularity, and the ORM turns a NULL float into 0.0,
        # which would hide the rows imported before min/max existed
        self.env.cr.execute(
            f"""
            SELECT date_trunc(%s, timestamp) AS bucket, {SERIES_COLUMNS}
              FROM ups_sample
             WHERE device_id = %s AND timestamp BETWEEN %s AND %s
          GROUP BY bucket ORDER BY bucket
            """, (bucket, device.id, start, end))
        series = [[_ms(row[0]), *row[1:]] for row in self.env.cr.fetchall()]

        outages = self.env['ups.outage'].search([
            ('device_id', '=', device.id), ('start', '<=', end), '|', ('end', '=', False), ('end', '>=', start)])
        return {
            'devices': [{'id': d.id, 'name': d.name} for d in devices],
            'device': self._device_info(device),
            'range': {'from': _ms(start), 'to': _ms(end), 'bucket': bucket, 'first': _ms(first)},
            'series': series,
            'outages': [{
                'start': _ms(o.start), 'end': _ms(o.end), 'duration': o.duration,
                'min_charge': o.min_charge, 'low_battery': o.low_battery,
            } for o in outages[:200]],
            'histogram': self._voltage_histogram(device, start, end),
            'stats': self._stats(device, start, end, now),
        }

    @api.model
    def _device_info(self, device):
        nut = json.loads(device.vars_json or '{}')
        return {
            'id': device.id, 'name': device.name, 'model': device.model, 'manufacturer': device.manufacturer,
            'serial': device.serial, 'status': device.status, 'on_battery': device.on_battery,
            'agent_state': device.agent_state, 'last_seen': _ms(device.last_seen),
            'battery_charge': device.battery_charge, 'battery_runtime': device.battery_runtime,
            'battery_voltage': device.battery_voltage, 'input_voltage': device.input_voltage,
            'ups_load': device.ups_load, 'nominal_power': device.nominal_power,
            'transfer_low': device.transfer_low, 'transfer_high': device.transfer_high,
            'test_result': nut.get('ups.test.result'), 'firmware': nut.get('ups.firmware'),
            'manufactured': nut.get('ups.mfr.date'),
        }

    @api.model
    def _thresholds(self):
        params = self.env['ir.config_parameter'].sudo()
        return (float(params.get_param('ups_monitor.volt_low', 207)),
                float(params.get_param('ups_monitor.volt_high', 253)))

    @api.model
    def _voltage_histogram(self, device, start, end):
        """Minutes per 2 V band of mains voltage; blackouts (about 0 V) are left out."""
        self.env.cr.execute("""
            SELECT round(input_voltage / 2) * 2 AS band, count(*)
              FROM ups_sample
             WHERE device_id = %s AND timestamp BETWEEN %s AND %s AND input_voltage > 1
          GROUP BY band ORDER BY band
        """, (device.id, start, end))
        return [[int(band), count] for band, count in self.env.cr.fetchall()]

    @api.model
    def _stats(self, device, start, end, now):
        cr = self.env.cr
        low, high = self._thresholds()
        # "COALESCE(min, avg)": rows imported before min/max existed fall back to the average
        cr.execute("""
            SELECT count(*),
                   avg(input_voltage) FILTER (WHERE input_voltage > 1),
                   min(COALESCE(input_voltage_min, input_voltage)) FILTER (WHERE input_voltage > 1),
                   max(COALESCE(input_voltage_max, input_voltage)),
                   stddev_samp(input_voltage) FILTER (WHERE input_voltage > 1),
                   count(*) FILTER (WHERE COALESCE(input_voltage_min, input_voltage) > 1
                                      AND COALESCE(input_voltage_min, input_voltage) < %(low)s),
                   count(*) FILTER (WHERE COALESCE(input_voltage_max, input_voltage) > %(high)s),
                   avg(ups_load),
                   max(COALESCE(ups_load_max, ups_load)),
                   min(COALESCE(battery_charge_min, battery_charge)),
                   avg(battery_charge),
                   avg(battery_runtime),
                   min(COALESCE(battery_voltage_min, battery_voltage)) FILTER (WHERE battery_voltage > 1)
              FROM ups_sample
             WHERE device_id = %(device)s AND timestamp BETWEEN %(start)s AND %(end)s
        """, {'low': low, 'high': high, 'device': device.id, 'start': start, 'end': end})
        (count, v_avg, v_min, v_max, v_std, under, over, load_avg, load_max,
         charge_min, charge_avg, runtime_avg, bvolt_min) = cr.fetchone()

        cr.execute("""
            SELECT timestamp, COALESCE(ups_load_max, ups_load) FROM ups_sample
             WHERE device_id = %s AND timestamp BETWEEN %s AND %s AND COALESCE(ups_load_max, ups_load) IS NOT NULL
          ORDER BY 2 DESC, 1 DESC LIMIT 1
        """, (device.id, start, end))
        peak = cr.fetchone()

        # energy: load % x nominal watts x time until the next sample; gaps over one hour carry no data
        cr.execute("""
            SELECT COALESCE(SUM(ups_load * EXTRACT(EPOCH FROM (nxt - timestamp))), 0)
              FROM (SELECT timestamp, ups_load, LEAD(timestamp) OVER (ORDER BY timestamp) AS nxt
                      FROM ups_sample
                     WHERE device_id = %s AND timestamp BETWEEN %s AND %s AND ups_load IS NOT NULL) s
             WHERE nxt IS NOT NULL AND nxt - timestamp <= interval '1 hour'
        """, (device.id, start, end))
        load_seconds = float(cr.fetchone()[0])
        kwh = load_seconds / 100 * (device.nominal_power or 0) / 3.6e6

        span = max((end - start).total_seconds(), 1)
        Outage = self.env['ups.outage']
        clipped = []
        for outage in Outage.search([
                ('device_id', '=', device.id), ('start', '<=', end), '|', ('end', '=', False), ('end', '>=', start)]):
            seconds = (min(outage.end or now, end) - max(outage.start, start)).total_seconds()
            clipped.append(max(seconds, 0))
        on_battery = sum(clipped)
        last = Outage.search([('device_id', '=', device.id)], order='start desc', limit=1)
        return {
            'samples': count,
            'span_seconds': span,
            'availability': 100 * (1 - min(on_battery / span, 1)),
            'outages': len(clipped),
            'outages_long': sum(1 for s in clipped if s >= 60),
            'outages_total': Outage.search_count([('device_id', '=', device.id)]),
            'on_battery_seconds': on_battery,
            'outage_longest_seconds': max(clipped, default=0),
            'outage_average_seconds': on_battery / len(clipped) if clipped else 0,
            'since_last_outage_seconds': (
                (now - (last.end or now)).total_seconds() if last else None),
            'voltage': {'avg': v_avg, 'min': v_min, 'max': v_max, 'std': v_std,
                        'under_samples': under, 'over_samples': over, 'low': low, 'high': high},
            'load': {'avg': load_avg, 'max': load_max, 'peak_at': _ms(peak[0]) if peak else None,
                     'avg_watts': (load_avg or 0) * (device.nominal_power or 0) / 100,
                     'peak_watts': (load_max or 0) * (device.nominal_power or 0) / 100,
                     'kwh': kwh},
            'battery': {'min_charge': charge_min, 'avg_charge': charge_avg,
                        'avg_runtime': runtime_avg, 'min_voltage': bvolt_min},
        }
