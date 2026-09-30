#!/bin/sh
# Install the Odoo push agent on the Raspberry that already runs upsmon-collector.
# Run as root from this directory.
set -eu
install -m 0755 ups_odoo_push.py /opt/upsmon/ups_odoo_push.py
if [ ! -f /etc/upsmon/odoo-push.env ]; then
    install -m 0640 -o root -g upsmon odoo-push.env.example /etc/upsmon/odoo-push.env
    echo "Edit /etc/upsmon/odoo-push.env (ODOO_URL, ODOO_TOKEN), then re-run this script."
    exit 0
fi
install -m 0644 upsmon-odoo-push.service /etc/systemd/system/upsmon-odoo-push.service
systemctl daemon-reload
systemctl enable --now upsmon-odoo-push.service
systemctl restart upsmon-odoo-push.service
systemctl --no-pager status upsmon-odoo-push.service | head -5
