# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The bot created by telegram_bot's migration ran the fuel conversation: mark it so."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['telegram.bot'].with_context(active_test=False).search([('kind', '=', 'generic')]).write({'kind': 'fuel'})
