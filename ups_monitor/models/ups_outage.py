# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import api, fields, models


class UpsOutage(models.Model):
    _name = 'ups.outage'
    _description = "UPS Mains Outage"
    _order = 'start desc'

    device_id = fields.Many2one('ups.device', required=True, index=True, ondelete='cascade')
    start = fields.Datetime(required=True, index=True)
    end = fields.Datetime(help="Empty while the UPS still runs on battery.")
    duration = fields.Float(compute='_compute_duration', help="Minutes on battery.")
    min_charge = fields.Float(help="Lowest battery charge during the outage (%).")
    low_battery = fields.Boolean(help="The UPS raised the low-battery flag.")

    @api.depends('start', 'end')
    def _compute_duration(self):
        now = fields.Datetime.now()
        for outage in self:
            outage.duration = ((outage.end or now) - outage.start).total_seconds() / 60 if outage.start else 0.0

    def _close(self, end):
        """Stamp the end and the lowest charge measured in between."""
        self.ensure_one()
        low = self.env['ups.sample']._read_group(
            [('device_id', '=', self.device_id.id), ('timestamp', '>=', self.start), ('timestamp', '<=', end)],
            aggregates=['battery_charge:min'],
        )[0][0]
        self.write({'end': end, 'min_charge': low or 0.0})
