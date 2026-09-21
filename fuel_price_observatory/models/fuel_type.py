# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

REGISTRY_URL = 'https://carburanti.mise.gov.it/ospzApi/registry/fuels'
# the registry ids read "<code>-<mode>": -1 self service, -0 served, -x either.
# Checked against the data on 2026-09-21: a search with 2-1 returns every self row of the
# region and only the served rows of those same stations, 2-0 the other way round, and on
# the 922 stations selling both, self never costs more (0.169 less on average).
FAMILY_SUFFIX = '-x'


class FuelType(models.Model):
    """Fuel families published by MIMIT, refreshed by both syncs so the UI can order them."""
    _name = 'fuel.type'
    _description = "Fuel Type"
    _order = 'sequence, id'

    code = fields.Integer("MIMIT Code", required=True, index=True,
                          help="Identifier MIMIT uses for this family (1 petrol, 2 diesel, 3 CNG, 4 LPG, ...).")
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10, help="Order the registry lists the family in.")

    _code_unique = models.Constraint(
        'unique (code)',
        "This fuel code is already registered.",
    )

    @api.model
    def _fetch_registry(self):
        """Return the registry entries. Tests patch this method."""
        response = requests.get(REGISTRY_URL, timeout=30)
        response.raise_for_status()
        return response.json().get('results') or []

    @api.model
    def _sync_fuel_types(self):
        """Upsert the families from the registry, keeping the order it publishes."""
        try:
            entries = self._fetch_registry()
        except (requests.RequestException, ValueError) as error:
            _logger.warning("Fuel registry unreachable: %s", error)
            return False
        existing = {record.code: record for record in self.search([])}
        sequence = 0
        for entry in entries:
            key = str(entry.get('id') or '')
            if not key.endswith(FAMILY_SUFFIX):
                continue
            code = key[:-len(FAMILY_SUFFIX)]
            name = (entry.get('description') or '').strip()
            if not code.isdigit() or not name:
                continue
            sequence += 10
            vals = {'code': int(code), 'name': name, 'sequence': sequence}
            record = existing.get(int(code))
            if record:
                changed = {key: value for key, value in vals.items() if record[key] != value}
                if changed:
                    record.write(changed)
            else:
                self.create(vals)
        _logger.info("Fuel registry: %s families cached", self.search_count([]))
        return True
