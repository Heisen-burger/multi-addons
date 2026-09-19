# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fuel_telegram_nearest_limit = fields.Integer("Nearest Stations", default=10,
                                                 config_parameter='fuel_telegram.nearest_limit',
                                                 help="Stations returned when a user sends a location.")
