# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class UpsEvent(models.Model):
    _name = 'ups.event'
    _description = "UPS Event"
    _order = 'timestamp desc, id desc'

    device_id = fields.Many2one('ups.device', required=True, index=True, ondelete='cascade')
    remote_id = fields.Integer(help="Event id in the Raspberry SQLite database; makes retries idempotent.")
    timestamp = fields.Datetime(required=True, index=True)
    kind = fields.Selection([
        ('status_change', "Status change"),
        ('comm_lost', "UPS communication lost"),
        ('comm_ok', "UPS communication restored"),
    ], required=True)
    old_status = fields.Char()
    new_status = fields.Char()
    detail = fields.Char()

    _device_remote_uniq = models.Constraint(
        'unique (device_id, remote_id)',
        "This event was already received.",
    )
