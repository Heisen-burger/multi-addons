# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import fields, models


class TelegramMediaDownload(models.Model):
    """One row per link received: what was asked, by whom, and how it ended."""
    _name = 'telegram.media.download'
    _description = "Telegram Media Download"
    _order = 'create_date desc, id desc'

    chat_id = fields.Many2one('telegram.chat', required=True, index=True, ondelete='cascade')
    url = fields.Char(required=True)
    provider = fields.Char(help="Provider that handled the link.")
    title = fields.Char()
    performer = fields.Char()
    size = fields.Integer("Size (bytes)")
    state = fields.Selection([
        ('pending', "Pending"), ('done', "Sent"), ('unsupported', "Unsupported link"),
        ('too_big', "Too big"), ('error', "Error"),
    ], default='pending', required=True, index=True)
    error = fields.Text()
