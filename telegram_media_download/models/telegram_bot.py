# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class TelegramBot(models.Model):
    _inherit = 'telegram.bot'

    kind = fields.Selection(selection_add=[('media', "Media download")], ondelete={'media': 'set default'})
