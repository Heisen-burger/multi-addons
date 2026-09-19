# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    telegram_media_suno_client_cookie = fields.Char(
        "Suno Session Cookie", config_parameter='telegram_media.suno_client_cookie',
        help="Value of the __client cookie of a logged-in suno.com session. Lets the bot download your "
             "own and private tracks. Leave empty for public tracks only.")
