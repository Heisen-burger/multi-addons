# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class FuelPrice(models.Model):
    _name = 'fuel.price'
    _description = "Fuel Price History"
    _order = 'date_communicated desc, id desc'

    station_fuel_id = fields.Many2one('fuel.station.fuel', string="Price List", required=True,
                                      index=True, ondelete='cascade')
    station_id = fields.Many2one(related='station_fuel_id.station_id', store=True)
    fuel_type = fields.Char(related='station_fuel_id.fuel_type', store=True)
    is_self = fields.Boolean(related='station_fuel_id.is_self', store=True)
    price = fields.Float(digits=(6, 3), required=True)
    previous_price = fields.Float(digits=(6, 3), help="Price before this change, 0 on the first row.")
    date_communicated = fields.Datetime(required=True, index=True,
                                        help="When the station communicated the new price.")
    mimit_price_id = fields.Integer("MIMIT Price ID")

    _key_unique = models.Constraint(
        'unique (station_fuel_id, mimit_price_id)',
        "This price communication is already archived.",
    )
    _history_idx = models.Index("(station_fuel_id, date_communicated DESC)")
