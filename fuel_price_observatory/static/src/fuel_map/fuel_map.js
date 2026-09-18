// STeSI Consulting - Michele Di Croce
// License OPL-1 (https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html).
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const LIB = "/fuel_price_observatory/static/lib/leaflet/";
const MIN_ZOOM = 9;
const MAX_MARKERS = 500;

export class FuelMap extends Component {
    static template = "fuel_price_observatory.FuelMap";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.mapRef = useRef("map");
        this.state = useState({
            fuelTypes: [],
            fuelType: "Gasolio",
            isSelf: true,
            count: 0,
            zoomedOut: false,
        });
        onMounted(() => this.start());
        onWillUnmount(() => this.map && this.map.remove());
    }

    async start() {
        const [groups] = await Promise.all([
            this.orm.formattedReadGroup("fuel.station.fuel", [], ["fuel_type"], ["__count"]),
            loadJS(LIB + "leaflet.js"),
            loadCSS(LIB + "leaflet.css"),
        ]);
        this.state.fuelTypes = groups
            .sort((a, b) => b.__count - a.__count)
            .map((g) => g.fuel_type);
        this.map = L.map(this.mapRef.el).setView([42.5, 12.5], 6);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this.map);
        this.layer = L.layerGroup().addTo(this.map);
        this.map.on("moveend", () => this.refresh());
        this.map.on("popupopen", (ev) => {
            const button = ev.popup.getElement().querySelector("[data-id]");
            button.addEventListener("click", () => this.openRecord(Number(button.dataset.id)));
        });
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (pos) => this.map.setView([pos.coords.latitude, pos.coords.longitude], 12),
                () => this.refresh()
            );
        } else {
            this.refresh();
        }
    }

    onFilterChange(field, value) {
        this.state[field] = value;
        this.refresh();
    }

    async refresh() {
        this.layer.clearLayers();
        this.state.zoomedOut = this.map.getZoom() < MIN_ZOOM;
        if (this.state.zoomedOut) {
            this.state.count = 0;
            return;
        }
        const b = this.map.getBounds();
        const rows = await this.orm.searchRead(
            "fuel.station.fuel",
            [
                ["fuel_type", "=", this.state.fuelType],
                ["is_self", "=", this.state.isSelf],
                ["current_price", ">", 0],
                ["latitude", ">=", b.getSouth()],
                ["latitude", "<=", b.getNorth()],
                ["longitude", ">=", b.getWest()],
                ["longitude", "<=", b.getEast()],
            ],
            ["display_name", "brand", "city", "current_price", "current_date", "min_price", "max_price",
             "latitude", "longitude", "message_is_follower"],
            { limit: MAX_MARKERS, order: "current_price" }
        );
        this.state.count = rows.length;
        if (!rows.length) {
            return;
        }
        const low = rows[0].current_price;
        const high = rows[rows.length - 1].current_price;
        for (const row of rows) {
            const ratio = high > low ? (row.current_price - low) / (high - low) : 0;
            L.circleMarker([row.latitude, row.longitude], {
                radius: 9,
                color: "#333",
                weight: row.message_is_follower ? 3 : 1,
                fillColor: `hsl(${Math.round(120 - 120 * ratio)}, 80%, 45%)`,
                fillOpacity: 0.9,
            })
                .bindPopup(this.popupHtml(row))
                .addTo(this.layer);
        }
    }

    popupHtml(row) {
        const esc = (s) => String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
        // babel only extracts _t() outside template literals
        const minLabel = _t("Min");
        const maxLabel = _t("Max");
        const openLabel = _t("Open");
        const updatedLabel = _t("Updated");
        const updated = row.current_date ? formatDateTime(deserializeDateTime(row.current_date)) : "";
        return `<div class="o_fuel_map_popup">
            <b>${esc(row.display_name)}</b><br/>
            <small>${esc(row.brand)} ${esc(row.city)}</small><br/>
            <span class="fs-4">${row.current_price.toFixed(3)} €</span><br/>
            <small>${esc(updatedLabel)} ${esc(updated)}</small><br/>
            <small>${esc(minLabel)} ${row.min_price.toFixed(3)} · ${esc(maxLabel)} ${row.max_price.toFixed(3)}</small><br/>
            <button class="btn btn-sm btn-primary mt-2" data-id="${row.id}">${esc(openLabel)}</button>
        </div>`;
    }

    openRecord(resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "fuel.station.fuel",
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("fuel_price_observatory.map", FuelMap);
