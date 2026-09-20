# STeSI Consulting - Michele Di Croce
# License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).


def migrate(cr, version):
    """Fill previous_price from the latest history row of every price list."""
    cr.execute("""
        UPDATE fuel_station_fuel f
           SET previous_price = p.previous_price
          FROM (
                SELECT DISTINCT ON (station_fuel_id) station_fuel_id, previous_price
                  FROM fuel_price
                 ORDER BY station_fuel_id, date_communicated DESC, id DESC
               ) p
         WHERE p.station_fuel_id = f.id
           AND COALESCE(f.previous_price, 0) = 0
    """)
