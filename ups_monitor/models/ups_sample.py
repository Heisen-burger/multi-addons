# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models

# NUT variable -> column. Variables outside this map are dropped on ingest.
METRICS = {
    'battery.charge': 'battery_charge',
    'battery.runtime': 'battery_runtime',
    'battery.voltage': 'battery_voltage',
    'input.voltage': 'input_voltage',
    'ups.load': 'ups_load',
}


class UpsSample(models.Model):
    _name = 'ups.sample'
    _description = "UPS Sample"
    _order = 'timestamp desc'
    _log_access = False  # 1440 rows per day per UPS: skip the four audit columns

    device_id = fields.Many2one('ups.device', required=True, index=True, ondelete='cascade')
    timestamp = fields.Datetime(required=True, index=True)
    battery_charge = fields.Float(aggregator='avg', help="Battery charge (%).")
    battery_runtime = fields.Float(aggregator='avg', help="Estimated runtime on battery (seconds).")
    battery_voltage = fields.Float(aggregator='avg', help="Battery voltage (V).")
    input_voltage = fields.Float(aggregator='avg', help="Mains input voltage (V).")
    ups_load = fields.Float("Load", aggregator='avg', help="UPS load (%).")

    _device_timestamp_uniq = models.Constraint(
        'unique (device_id, timestamp)',
        "The UPS already has a sample at this time.",
    )
