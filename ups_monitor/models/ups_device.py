# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import json
from datetime import datetime, timedelta, timezone

from odoo import _, api, fields, models

from .ups_sample import METRICS

MAX_SAMPLES = 2000
MAX_EVENTS = 500
NOTIFY_WINDOW = timedelta(hours=1)  # older events (catch-up after a downtime) stay silent


def _to_dt(epoch):
    return datetime.fromtimestamp(int(epoch), timezone.utc).replace(tzinfo=None)


class UpsDevice(models.Model):
    _name = 'ups.device'
    _description = "UPS"
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    serial = fields.Char(required=True, index=True, copy=False)
    manufacturer = fields.Char()
    model = fields.Char()
    active = fields.Boolean(default=True)
    last_seen = fields.Datetime(readonly=True, help="Last time the Raspberry agent reached Odoo.")
    agent_state = fields.Selection(
        [('online', "Agent online"), ('offline', "Agent offline")],
        default='offline', readonly=True, tracking=True)
    status = fields.Char(readonly=True, help="Raw NUT status: OL online, OB on battery, LB low battery, CHRG, DISCHRG.")
    on_battery = fields.Boolean(readonly=True)
    battery_charge = fields.Float(readonly=True)
    battery_runtime = fields.Float(readonly=True)
    battery_voltage = fields.Float(readonly=True)
    input_voltage = fields.Float(readonly=True)
    ups_load = fields.Float("Load", readonly=True, help="UPS load (%).")
    vars_json = fields.Text("NUT variables", readonly=True)
    outage_count = fields.Integer(compute='_compute_outage_count')

    _serial_uniq = models.Constraint('unique (serial)', "A UPS with this serial already exists.")

    def _compute_outage_count(self):
        counts = dict(self.env['ups.outage']._read_group(
            [('device_id', 'in', self.ids)], ['device_id'], ['__count']))
        for device in self:
            device.outage_count = counts.get(device, 0)

    def action_open_outages(self):
        self.ensure_one()
        domain = [('device_id', '=', self.id)]  # built before _(): the extractor reads a tuple after _() as a msgid
        return {
            'type': 'ir.actions.act_window',
            'name': _("Outages"),
            'res_model': 'ups.outage',
            'view_mode': 'list,form,graph',
            'domain': domain,
            'context': {'default_device_id': self.id},
        }

    def action_open_charts(self):
        self.ensure_one()
        domain = [('device_id', '=', self.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _("Charts"),
            'res_model': 'ups.sample',
            'view_mode': 'graph,pivot,list',
            'domain': domain,
            'context': {'graph_measure': 'input_voltage', 'graph_mode': 'line'},
        }

    # -- ingest ---------------------------------------------------------------
    @api.model
    def _ingest(self, payload):
        """Store one batch pushed by the agent. Every part is idempotent: a retried batch changes nothing."""
        info = payload.get('device') or {}
        serial = str(info.get('serial') or '').strip()
        if not serial:
            raise ValueError("device.serial is required")
        device = self.with_context(active_test=False).search([('serial', '=', serial)], limit=1)
        if not device:
            device = self.create({
                'serial': serial,
                'name': info.get('name') or ' '.join(filter(None, [info.get('manufacturer'), info.get('model')])) or serial,
                'manufacturer': info.get('manufacturer'),
                'model': info.get('model'),
            })
        # samples first: closing an outage reads the lowest charge from them
        samples = device._ingest_samples((payload.get('samples') or [])[:MAX_SAMPLES])
        events = device._ingest_events((payload.get('events') or [])[:MAX_EVENTS])
        device._ingest_state(payload.get('vars') or {})
        return {'samples': samples, 'events': events}

    def _ingest_samples(self, rows):
        parsed = {}
        for row in rows:
            try:
                values = row['m']
                parsed[_to_dt(row['ts'])] = {col: float(values[var]) for var, col in METRICS.items() if var in values}
            except (KeyError, TypeError, ValueError):
                continue
        if not parsed:
            return 0
        known = set(self.env['ups.sample'].search(
            [('device_id', '=', self.id), ('timestamp', 'in', list(parsed))]).mapped('timestamp'))
        vals_list = [
            {'device_id': self.id, 'timestamp': ts, **vals}
            for ts, vals in parsed.items() if ts not in known
        ]
        self.env['ups.sample'].create(vals_list)
        return len(vals_list)

    def _ingest_events(self, rows):
        valid = []
        for row in rows:
            try:
                valid.append({
                    'device_id': self.id,
                    'remote_id': int(row['id']),
                    'timestamp': _to_dt(row['ts']),
                    'kind': row['kind'],
                    'old_status': row.get('old'),
                    'new_status': row.get('new'),
                    'detail': row.get('detail'),
                })
            except (KeyError, TypeError, ValueError):
                continue
        known = set(self.env['ups.event'].search(
            [('device_id', '=', self.id), ('remote_id', 'in', [v['remote_id'] for v in valid])]).mapped('remote_id'))
        created = 0
        for vals in sorted(valid, key=lambda v: (v['timestamp'], v['remote_id'])):
            if vals['remote_id'] in known or vals['kind'] not in dict(self.env['ups.event']._fields['kind'].selection):
                continue
            event = self.env['ups.event'].create(vals)
            created += 1
            if event.kind == 'status_change':
                self._track_outage(event)
        return created

    def _track_outage(self, event):
        """Open an outage when the UPS reports OB (on battery), close it when OB disappears."""
        flags = (event.new_status or '').split()
        ongoing = self.env['ups.outage'].search([('device_id', '=', self.id), ('end', '=', False)], limit=1)
        recent = fields.Datetime.now() - event.timestamp < NOTIFY_WINDOW
        if 'OB' in flags and not ongoing:
            self.env['ups.outage'].create({
                'device_id': self.id, 'start': event.timestamp, 'low_battery': 'LB' in flags})
            if recent:
                self.message_post(body=_("Mains power lost: the UPS runs on battery."), subtype_xmlid='mail.mt_comment')
        elif 'OB' in flags and 'LB' in flags:
            ongoing.low_battery = True
        elif 'OB' not in flags and ongoing:
            ongoing._close(event.timestamp)
            if recent:
                self.message_post(
                    body=_("Mains power restored after %.1f minutes.", ongoing.duration), subtype_xmlid='mail.mt_comment')

    def _ingest_state(self, vars_):
        vals = {'last_seen': fields.Datetime.now(), 'agent_state': 'online'}
        if vars_:
            status = str(vars_.get('ups.status') or '')
            vals.update(status=status, on_battery='OB' in status.split(), vars_json=json.dumps(vars_, indent=1, sort_keys=True))
            for var, col in METRICS.items():
                try:
                    vals[col] = float(vars_[var])
                except (KeyError, TypeError, ValueError):
                    pass
        if self.agent_state == 'offline' and self.last_seen:
            self.message_post(body=_("The Raspberry agent is back online."), subtype_xmlid='mail.mt_comment')
        self.write(vals)

    # -- cron -----------------------------------------------------------------
    @api.model
    def _cron_check_agents(self):
        minutes = int(self.env['ir.config_parameter'].sudo().get_param('ups_monitor.offline_minutes', 5))
        stale = self.search([
            ('agent_state', '=', 'online'), ('last_seen', '<', fields.Datetime.now() - timedelta(minutes=minutes))])
        for device in stale:
            device.agent_state = 'offline'
            device.message_post(
                body=_("No data from the Raspberry agent for %s minutes.", minutes), subtype_xmlid='mail.mt_comment')

    @api.model
    def _cron_purge_samples(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param('ups_monitor.retention_days', 90))
        self.env['ups.sample'].search([('timestamp', '<', fields.Datetime.now() - timedelta(days=days))]).unlink()
