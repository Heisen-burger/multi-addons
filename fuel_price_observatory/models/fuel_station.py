# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import csv
import logging

import requests

from odoo import api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

REGISTRY_CSV_URL = 'https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv'
# idImpianto|Gestore|Bandiera|Tipo Impianto|Nome Impianto|Indirizzo|Comune|Provincia|Latitudine|Longitudine
CSV_COLUMNS = 10


class FuelStation(models.Model):
    _name = 'fuel.station'
    _description = "Fuel Station"
    _order = 'name, id'

    mimit_id = fields.Integer("MIMIT ID", required=True, index=True,
                              help="Station identifier in the MIMIT observatory (idImpianto).")
    name = fields.Char(required=True)
    brand = fields.Char(index=True)
    manager = fields.Char(help="Company operating the station (Gestore).")
    station_type = fields.Char(help="Road or motorway station (Tipo Impianto).")
    address = fields.Char(help="Full address string as published by the observatory API.")
    street = fields.Char()
    city = fields.Char(index=True)
    province = fields.Char(index=True)
    latitude = fields.Float(digits=(10, 6))
    longitude = fields.Float(digits=(10, 6))
    active = fields.Boolean(default=True)
    fuel_ids = fields.One2many('fuel.station.fuel', 'station_id', string="Price List")

    _mimit_id_unique = models.Constraint(
        'unique (mimit_id)',
        "A station with this MIMIT ID already exists.",
    )

    @api.model
    def _fetch_registry_csv(self):
        """Return the registry CSV text. Tests patch this method."""
        response = requests.get(REGISTRY_CSV_URL, timeout=120)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _cron_sync_stations(self):
        """Upsert stations from the daily MIMIT registry CSV.

        Line 1 carries the extraction date, line 2 the header. Rows with a column count
        other than 10 hide a pipe inside the address and get skipped. Stations missing
        from the CSV are archived: the file lists active stations only.
        """
        self.env['fuel.type']._sync_fuel_types()
        lines = self._fetch_registry_csv().splitlines()[2:]
        rows = list(csv.reader(lines, delimiter='|'))
        bad = sum(1 for row in rows if len(row) != CSV_COLUMNS)
        if bad:
            _logger.warning("Fuel registry: skipped %s malformed rows", bad)

        existing = {s.mimit_id: s for s in self.with_context(active_test=False).search([])}
        seen = set()
        to_create = []
        for row in rows:
            if len(row) != CSV_COLUMNS:
                continue
            row = [' '.join(cell.split()) for cell in row]  # trims and collapses inner tabs
            if not row[0].isdigit():
                continue
            mimit_id = int(row[0])
            seen.add(mimit_id)
            vals = {
                'mimit_id': mimit_id,
                'manager': row[1],
                'brand': row[2],
                'station_type': row[3],
                'name': row[4] or row[2] or str(mimit_id),
                'street': row[5],
                'city': row[6],
                'province': row[7],
                'latitude': self._to_float(row[8]),
                'longitude': self._to_float(row[9]),
                'active': True,
            }
            station = existing.get(mimit_id)
            if not station:
                to_create.append(vals)
                continue
            changed = {
                key: value for key, value in vals.items()
                if (float_compare(station[key], value, precision_digits=6) if key in ('latitude', 'longitude')
                    else station[key] != value)
            }
            if changed:
                station.write(changed)
        created = self.create(to_create)
        gone = self.browse([s.id for mid, s in existing.items() if mid not in seen and s.active])
        gone.write({'active': False})
        _logger.info("Fuel registry: %s created, %s archived, %s total rows",
                     len(created), len(gone), len(rows))
        return True
