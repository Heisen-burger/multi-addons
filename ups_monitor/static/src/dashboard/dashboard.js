import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const HOUR = 3600 * 1000;
const PRESETS = [
    { key: "1h", label: _t("1 hour"), ms: HOUR },
    { key: "6h", label: _t("6 hours"), ms: 6 * HOUR },
    { key: "24h", label: _t("24 hours"), ms: 24 * HOUR },
    { key: "7d", label: _t("7 days"), ms: 7 * 24 * HOUR },
    { key: "30d", label: _t("30 days"), ms: 30 * 24 * HOUR },
    { key: "90d", label: _t("90 days"), ms: 90 * 24 * HOUR },
    { key: "all", label: _t("All"), ms: null },
];
const BUCKET_MS = { minute: 60 * 1000, hour: HOUR, day: 24 * HOUR };

// columns of one series row, as sent by ups.dashboard.get_data
const [T, V, V_MIN, V_MAX, CHARGE, CHARGE_MIN, LOAD, LOAD_MAX, RUNTIME, RUNTIME_MIN, BVOLT, BVOLT_MIN] =
    Array.from({ length: 12 }, (_, i) => i);

const ORANGE = "#F1972B";
const BLUE = "#3b82f6";
const RED = "#dc3545";
const GREEN = "#28a745";
const GRID = "rgba(128, 128, 128, 0.2)";

/** Shades the periods spent on battery behind every chart. */
const outageBands = {
    id: "outageBands",
    beforeDatasetsDraw(chart, _args, options) {
        const x = chart.scales.x;
        if (!options?.bands || !x) {
            return;
        }
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.fillStyle = "rgba(220, 53, 69, 0.22)";
        for (const band of options.bands) {
            if (band.to < x.min || band.from > x.max) {
                continue;
            }
            const left = Math.max(x.getPixelForValue(band.from), chartArea.left);
            const right = Math.min(x.getPixelForValue(band.to), chartArea.right);
            // at least 2 px, so a ten-second outage stays visible on a 30-day chart
            ctx.fillRect(left, chartArea.top, Math.max(right - left, 2), chartArea.bottom - chartArea.top);
        }
        ctx.restore();
    },
};

function fmt(value, digits = 1) {
    if (value === null || value === undefined) {
        return "-";
    }
    return Number(value).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}

function fmtDuration(seconds) {
    if (seconds === null || seconds === undefined) {
        return "-";
    }
    const s = Math.round(seconds);
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d) {
        return `${d} d ${h} h`;
    }
    if (h) {
        return `${h} h ${m} min`;
    }
    if (m) {
        return `${m} min ${s % 60} s`;
    }
    return `${s} s`;
}

/** Epoch milliseconds -> value of an <input type="datetime-local"> in the browser time zone. */
function toLocalInput(ms) {
    const d = new Date(ms - new Date(ms).getTimezoneOffset() * 60000);
    return d.toISOString().slice(0, 16);
}

function fmtDate(ms) {
    return ms ? new Date(ms).toLocaleString() : "-";
}

export class UpsDashboard extends Component {
    static template = "ups_monitor.Dashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.presets = PRESETS.map((p) => ({ ...p, label: String(p.label) }));
        this.voltageRef = useRef("voltage");
        this.batteryRef = useRef("battery");
        this.runtimeRef = useRef("runtime");
        this.histogramRef = useRef("histogram");
        this.charts = [];
        this.timer = null;
        this.state = useState({
            deviceId: this.props.action?.context?.default_device_id || null,
            preset: "24h",
            shift: 0, // how many periods back from now
            customFrom: "", // datetime-local values of the custom range
            customTo: "",
            data: null,
            loading: false,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.schedule());
        onWillUnmount(() => {
            clearTimeout(this.timer);
            this.destroyCharts();
        });
        useEffect(
            () => this.renderCharts(),
            () => [this.state.data]
        );
    }

    // -- data ---------------------------------------------------------------
    get period() {
        if (this.state.preset === "custom") {
            return { from: new Date(this.state.customFrom).getTime(), to: new Date(this.state.customTo).getTime() };
        }
        const preset = PRESETS.find((p) => p.key === this.state.preset);
        if (!preset.ms) {
            return { from: null, to: null };
        }
        const to = Date.now() - this.state.shift * preset.ms;
        return { from: to - preset.ms, to };
    }

    async load() {
        this.state.loading = true;
        try {
            const { from, to } = this.period;
            this.state.data = await this.orm.call("ups.dashboard", "get_data", [], {
                device_id: this.state.deviceId,
                date_from: from,
                date_to: to,
            });
            this.state.deviceId = this.state.data.device?.id || null;
            if (this.state.preset !== "custom" && this.state.data.range) {
                // the date fields follow the preset, so "Apply" starts from what the charts show
                this.state.customFrom = toLocalInput(this.state.data.range.from);
                this.state.customTo = toLocalInput(this.state.data.range.to);
            }
        } finally {
            this.state.loading = false;
        }
    }

    /** Refresh while the window ends "now": every 5 s on battery, every 30 s otherwise. */
    schedule() {
        clearTimeout(this.timer);
        const onBattery = this.state.data?.device?.on_battery;
        this.timer = setTimeout(async () => {
            if (this.state.shift === 0 && this.state.preset !== "custom") {
                try {
                    await this.load();
                } catch {
                    // the server may be restarting: try again at the next tick
                }
            }
            this.schedule();
        }, onBattery ? 5000 : 30000);
    }

    async reload() {
        await this.load();
        this.schedule();
    }

    selectPreset(key) {
        this.state.preset = key;
        this.state.shift = 0;
        return this.reload();
    }

    get customValid() {
        // an empty field gives NaN, and any comparison with NaN is false
        return new Date(this.state.customFrom).getTime() < new Date(this.state.customTo).getTime();
    }

    applyCustom() {
        if (!this.customValid) {
            return;
        }
        this.state.preset = "custom";
        this.state.shift = 0;
        return this.reload();
    }

    move(direction) {
        this.state.shift = Math.max(0, this.state.shift + direction);
        return this.reload();
    }

    selectDevice(ev) {
        this.state.deviceId = parseInt(ev.target.value);
        return this.reload();
    }

    // -- display helpers ------------------------------------------------------
    get canMove() {
        return this.state.preset !== "all" && this.state.preset !== "custom";
    }

    get periodLabel() {
        const range = this.state.data?.range;
        return range ? `${fmtDate(range.from)}  ->  ${fmtDate(range.to)}` : "";
    }

    get bucketLabel() {
        return { minute: _t("one point per minute"), hour: _t("one point per hour"), day: _t("one point per day") }[
            this.state.data?.range?.bucket
        ];
    }

    get statusClass() {
        const device = this.state.data.device;
        if (device.on_battery) {
            return "text-bg-danger";
        }
        return (device.status || "").split(" ").includes("OL") ? "text-bg-success" : "text-bg-secondary";
    }

    get statGroups() {
        const s = this.state.data.stats;
        const device = this.state.data.device;
        const v = s.voltage;
        const l = s.load;
        const b = s.battery;
        const watts = (value) => (value ? `${fmt(value, 0)} W` : "-");
        return [
            {
                title: _t("Mains availability"),
                items: [
                    { label: _t("Availability"), value: `${fmt(s.availability, 3)} %` },
                    { label: _t("Outages in period"), value: `${s.outages} (${s.outages_long} >= 1 min)` },
                    { label: _t("Time on battery"), value: fmtDuration(s.on_battery_seconds) },
                    { label: _t("Longest outage"), value: fmtDuration(s.outage_longest_seconds) },
                    { label: _t("Average outage"), value: fmtDuration(s.outage_average_seconds) },
                    { label: _t("Since last outage"), value: fmtDuration(s.since_last_outage_seconds) },
                    { label: _t("Outages ever recorded"), value: s.outages_total },
                ],
            },
            {
                title: _t("Mains voltage"),
                items: [
                    { label: _t("Average"), value: `${fmt(v.avg)} V` },
                    { label: _t("Lowest"), value: `${fmt(v.min)} V` },
                    { label: _t("Highest"), value: `${fmt(v.max)} V` },
                    { label: _t("Standard deviation"), value: `${fmt(v.std, 2)} V` },
                    { label: _t("Minutes below %s V", v.low), value: v.under_samples, warn: v.under_samples > 0 },
                    { label: _t("Minutes above %s V", v.high), value: v.over_samples, warn: v.over_samples > 0 },
                ],
            },
            {
                title: _t("Load and energy"),
                items: [
                    { label: _t("Average load"), value: `${fmt(l.avg)} %  (${watts(l.avg_watts)})` },
                    { label: _t("Peak load"), value: `${fmt(l.max)} %  (${watts(l.peak_watts)})` },
                    { label: _t("Peak at"), value: fmtDate(l.peak_at) },
                    { label: _t("Energy"), value: `${fmt(l.kwh, 2)} kWh` },
                ],
            },
            {
                title: _t("Battery"),
                items: [
                    { label: _t("Lowest charge"), value: `${fmt(b.min_charge, 0)} %`, warn: b.min_charge < 50 },
                    { label: _t("Average charge"), value: `${fmt(b.avg_charge, 1)} %` },
                    { label: _t("Average runtime"), value: fmtDuration(b.avg_runtime) },
                    { label: _t("Lowest battery voltage"), value: `${fmt(b.min_voltage)} V` },
                    { label: _t("Last self-test"), value: device.test_result || "-" },
                    { label: _t("Firmware / built"), value: `${device.firmware || "-"} / ${device.manufactured || "-"}` },
                ],
            },
        ];
    }

    fmt = fmt;
    fmtDuration = fmtDuration;
    fmtDate = fmtDate;

    // -- charts ---------------------------------------------------------------
    destroyCharts() {
        for (const chart of this.charts) {
            chart.destroy();
        }
        this.charts = [];
    }

    renderCharts() {
        this.destroyCharts();
        const data = this.state.data;
        if (!data?.device || !this.voltageRef.el) {
            return;
        }
        const { series, range } = data;
        const bands = data.outages.map((o) => ({ from: o.start, to: o.end || range.to }));
        const gap = BUCKET_MS[range.bucket] * 3;
        const dotted = series.length < 150;

        // a line must break where samples are missing, not bridge the hole
        const points = (column, fallback) => {
            const out = [];
            let previous = null;
            for (const row of series) {
                if (previous !== null && row[T] - previous > gap) {
                    out.push({ x: previous + BUCKET_MS[range.bucket], y: null });
                }
                out.push({ x: row[T], y: row[column] ?? (fallback === undefined ? null : row[fallback]) });
                previous = row[T];
            }
            return out;
        };
        const line = (label, column, color, extra = {}, fallback) => ({
            label,
            data: points(column, fallback),
            borderColor: color,
            backgroundColor: color,
            borderWidth: 1.5,
            pointRadius: dotted ? 2 : 0,
            tension: 0,
            ...extra,
        });

        const text = getComputedStyle(document.body).color;
        const options = (yAxis, extraScales = {}) => ({
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            scales: {
                x: {
                    type: "time",
                    min: range.from,
                    max: range.to,
                    time: { tooltipFormat: "dd LLL HH:mm" },
                    grid: { color: GRID },
                    ticks: { color: text, maxRotation: 0 },
                },
                y: { grid: { color: GRID }, ticks: { color: text }, ...yAxis },
                ...extraScales,
            },
            plugins: {
                outageBands: { bands },
                legend: {
                    labels: {
                        color: text,
                        usePointStyle: true,
                        filter: (item, chartData) => !chartData.datasets[item.datasetIndex].noLegend,
                    },
                },
            },
        });
        const make = (ref, config) => this.charts.push(new Chart(ref.el, { plugins: [outageBands], ...config }));

        // mains voltage: the min-max band shows a dip inside a minute that the mean hides
        const volts = series.flatMap((r) => [r[V], r[V_MIN], r[V_MAX]]).filter((x) => x > 1);
        const yMin = volts.length ? Math.floor(Math.min(...volts) - 4) : undefined;
        const yMax = volts.length ? Math.ceil(Math.max(...volts) + 4) : undefined;
        const limit = (label, value, color) => ({
            label,
            data: [
                { x: range.from, y: value },
                { x: range.to, y: value },
            ],
            borderColor: color,
            borderDash: [6, 4],
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
        });
        const limits = [];
        const { low, high } = data.stats.voltage;
        if (yMin !== undefined && low > yMin) {
            limits.push(limit(_t("Low warning"), low, ORANGE));
        }
        if (yMin !== undefined && high < yMax) {
            limits.push(limit(_t("High warning"), high, ORANGE));
        }
        make(this.voltageRef, {
            type: "line",
            data: {
                datasets: [
                    line(_t("Minimum"), V_MIN, "rgba(59, 130, 246, 0)", { borderWidth: 0, noLegend: true }, V),
                    line(_t("Min-max range"), V_MAX, "rgba(59, 130, 246, 0)", {
                        borderWidth: 0,
                        backgroundColor: "rgba(59, 130, 246, 0.25)",
                        fill: "-1",
                    }, V),
                    line(_t("Average"), V, BLUE),
                    ...limits,
                ],
            },
            options: options({ min: yMin, max: yMax, title: { display: true, text: "V", color: text } }),
        });

        // battery charge and load share the 0-100 % axis
        make(this.batteryRef, {
            type: "line",
            data: {
                datasets: [
                    line(_t("Battery charge"), CHARGE, GREEN),
                    line(_t("Lowest charge"), CHARGE_MIN, GREEN, { borderDash: [3, 3], borderWidth: 1 }, CHARGE),
                    line(_t("Load"), LOAD, ORANGE),
                    line(_t("Peak load"), LOAD_MAX, ORANGE, { borderDash: [3, 3], borderWidth: 1 }, LOAD),
                ],
            },
            options: options({ min: 0, max: 100, title: { display: true, text: "%", color: text } }),
        });

        // runtime in minutes, battery voltage on the right axis
        const runtime = line(_t("Runtime (min)"), RUNTIME, BLUE, { fill: true, backgroundColor: "rgba(59, 130, 246, 0.12)" });
        runtime.data = runtime.data.map((p) => ({ x: p.x, y: p.y === null ? null : p.y / 60 }));
        make(this.runtimeRef, {
            type: "line",
            data: {
                datasets: [
                    runtime,
                    line(_t("Battery voltage (V)"), BVOLT, ORANGE, { yAxisID: "y1" }),
                ],
            },
            options: options(
                { beginAtZero: true, title: { display: true, text: "min", color: text } },
                { y1: { position: "right", grid: { drawOnChartArea: false }, ticks: { color: text }, title: { display: true, text: "V", color: text } } }
            ),
        });

        // how long the mains stayed at each voltage
        make(this.histogramRef, {
            type: "bar",
            data: {
                labels: data.histogram.map(([band]) => `${band}`),
                datasets: [
                    {
                        label: _t("Minutes at this voltage"),
                        data: data.histogram.map(([, count]) => count),
                        backgroundColor: data.histogram.map(([band]) =>
                            band < low || band > high ? RED : BLUE
                        ),
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { grid: { display: false }, ticks: { color: text }, title: { display: true, text: "V", color: text } },
                    // log scale: a few minutes at 200 V must stay visible next to thousands at 232 V
                    y: {
                        type: "logarithmic",
                        min: 0.5,
                        grid: { color: GRID },
                        ticks: {
                            color: text,
                            callback: (value) => ([1, 10, 100, 1000, 10000, 100000].includes(value) ? value : ""),
                        },
                    },
                },
                plugins: { legend: { display: false } },
            },
        });
    }
}

registry.category("actions").add("ups_monitor.dashboard", UpsDashboard);
