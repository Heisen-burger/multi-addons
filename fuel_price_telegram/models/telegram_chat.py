# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import api, fields, models


class TelegramChat(models.Model):
    """Fuel-bot state of a chat. The conversation itself lives in telegram.handler.fuel."""
    _inherit = 'telegram.chat'

    state = fields.Selection(selection_add=[('threshold', "Waiting for threshold")],
                             ondelete={'threshold': 'set default'})
    pending_subscription_id = fields.Many2one('fuel.telegram.subscription', ondelete='set null',
                                              help="Subscription whose threshold the next message sets.")
    last_station_id = fields.Many2one('fuel.station', ondelete='set null')
    fuel_type = fields.Char(help="Fuel used when the chat sends a location. '*' means every fuel.")
    is_self = fields.Boolean("Self Service", default=True)
    mode_chosen = fields.Boolean(help="The chat answered the self/served question at least once.")
    last_latitude = fields.Float(digits=(10, 6))
    last_longitude = fields.Float(digits=(10, 6))
    subscription_ids = fields.One2many('fuel.telegram.subscription', 'chat_id', string="Subscriptions")
    subscription_count = fields.Integer(compute='_compute_subscription_count')

    @api.depends('subscription_ids')
    def _compute_subscription_count(self):
        for chat in self:
            chat.subscription_count = len(chat.subscription_ids)

    def _reset_state(self):
        super()._reset_state()
        self.write({'pending_subscription_id': False})
