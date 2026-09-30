# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import hmac
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

_logger = logging.getLogger(__name__)

TOKEN_PARAM = 'ups_monitor.token'


class UpsMonitorController(http.Controller):

    @http.route(
        '/ups_monitor/ingest',
        type='json2',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
        # auth='none' routes default to a read-only cursor in 19.0, and this one writes
        readonly=False,
    )
    def ingest(self, **payload):
        """Receive one batch from the Raspberry agent.

        Body: {"device": {...}, "vars": {...}, "samples": [...], "events": [...]}.
        Authentication: "X-Auth-Token" header, compared to the 'ups_monitor.token' system parameter.
        A batch without samples and events works as a heartbeat.
        """
        # auth='none' leaves the environment without a user; the token is the only credential
        env = request.env(user=SUPERUSER_ID, su=True)
        token = env['ir.config_parameter'].get_param(TOKEN_PARAM)
        sent = request.httprequest.headers.get('X-Auth-Token', '')
        if not token or not hmac.compare_digest(sent.encode(), token.encode()):
            _logger.warning("UPS ingest rejected from %s", request.httprequest.remote_addr)
            return request.make_json_response({'status': 'forbidden'}, status=403)
        try:
            # the savepoint drops a half-written batch, which the agent then resends whole
            with env.cr.savepoint():
                result = env['ups.device']._ingest(payload)
        except ValueError as exc:
            return request.make_json_response({'status': 'invalid', 'error': str(exc)}, status=400)
        except Exception:
            _logger.exception("UPS ingest failed")
            return request.make_json_response({'status': 'error'}, status=500)
        return {'status': 'ok', **result}
