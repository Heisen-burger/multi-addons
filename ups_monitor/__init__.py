# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import secrets

from . import controllers, models


def _post_init_hook(env):
    """Create the shared ingest token once; the agent sends it in "X-Auth-Token"."""
    params = env['ir.config_parameter'].sudo()
    if not params.get_param(controllers.main.TOKEN_PARAM):
        params.set_param(controllers.main.TOKEN_PARAM, secrets.token_urlsafe(32))
