# UPS Monitor

[![License: OPL-1](https://img.shields.io/badge/licence-OPL--1-F1972B)](https://www.odoo.com/documentation/user/19.0/legal/licenses/licenses.html)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-F1972B)](https://www.odoo.com)
[![Maintained by STeSI](https://img.shields.io/badge/maintained%20by-STeSI%20Consulting-F1972B)](https://stesi.consulting)

A Raspberry Pi reads an APC UPS through NUT and pushes the data to Odoo. Odoo stores the
time series, detects mains outages and shows charts, outage history and events.

```
UPS --USB--> NUT --> upsmon-collector --> SQLite (buffer) --> upsmon-odoo-push --HTTPS--> Odoo
                                                                  (this module: agent/)
```

# Odoo side

| Menu | Content |
|---|---|
| UPS Monitor > Dashboard | Live tiles, charts and statistics for one period (see below). |
| UPS Monitor > UPS | One card per UPS: status, battery, load, mains voltage, agent state. Chatter receives the alerts. |
| UPS Monitor > Charts | Plain Odoo graph, pivot and list views of the samples, for ad-hoc grouping and export. |
| UPS Monitor > Mains outages | One record per outage: start, end, duration, lowest battery charge, low-battery flag. Bar graph per month. |
| UPS Monitor > Events | Status changes and UPS communication losses reported by the collector. |

An outage opens when the NUT status contains `OB` (on battery) and closes when `OB` disappears.
A status such as `OL DISCHRG` (self-test on mains) is not an outage.

## Dashboard

Presets: 1 hour, 6 hours, 24 hours, 7 days, 30 days, 90 days, all. The arrows move the window back and
forth. For any other period, set the From and To fields (date and time, browser time zone) and press
Apply. The fields follow the preset, so they start from what the charts show. The page refreshes itself
every 30 s, every 5 s while the UPS runs on battery; a custom period stays fixed.

- **Live tiles:** status, mains voltage, battery charge, load (also in watts), runtime, agent state.
- **Mains voltage:** average line and a shaded min-max band. A dip of a few seconds shows in the band
  even when the minute average stays flat. Dashed lines mark the warning thresholds.
- **Battery charge and load**, with their lowest and peak values as dotted lines.
- **Runtime and battery voltage.**
- **Voltage histogram:** minutes spent at each 2 V band, log scale, out-of-threshold bands in red.
- **Red bands** behind every chart mark the periods on battery.
- **Statistics:** availability %, outages (count, total, longest, average, time since the last),
  voltage average / lowest / highest / standard deviation and minutes outside the thresholds,
  average and peak load in % and W, energy in kWh, lowest and average battery charge, average runtime,
  lowest battery voltage, last self-test result.

One point per minute up to 2 days, per hour up to 120 days, per day beyond. Hours and days keep the
lowest and highest value of their minutes. Energy uses the load times the nominal power of the UPS
(`ups.realpower.nominal`), summed over the time between samples; gaps longer than one hour count as zero.
Rows older than the min-max feature (before 2026-09-30) fall back to the average.

## Models

| Model | Purpose |
|---|---|
| `ups.device` | One UPS, keyed by serial number. Latest values, agent state, chatter. Created on first contact. |
| `ups.sample` | One row per minute: mean, minimum and maximum of battery charge, runtime, battery voltage, input voltage and load. Unique per (device, timestamp). |
| `ups.event` | Status change or communication event. Unique per (device, remote id). |
| `ups.outage` | Mains outage derived from status-change events. |

## Alerts

`ups.device` posts a message (subtype Discussion, so followers get an email) when:

- mains power is lost and when it returns, with the duration;
- the agent stays silent longer than `ups_monitor.offline_minutes` (default 5) and when it returns.

Events older than one hour never notify. A backlog delivered after a downtime therefore stays quiet.

## Configuration

| System parameter | Default | Meaning |
|---|---|---|
| `ups_monitor.token` | random, set at install | Shared secret the agent sends in the `X-Auth-Token` header. Rotate it by editing the value. |
| `ups_monitor.offline_minutes` | 5 | Minutes without contact before the agent counts as offline. |
| `ups_monitor.retention_days` | 730 | Samples older than this are purged daily. Events and outages stay. |
| `ups_monitor.volt_low` | 207 | Mains voltage below which a minute counts as under-voltage (230 V -10 %). |
| `ups_monitor.volt_high` | 253 | Mains voltage above which a minute counts as over-voltage (230 V +10 %). |

Add the users who should receive alerts as followers of the UPS.

## Endpoint

`POST /ups_monitor/ingest`, header `X-Auth-Token`, flat JSON body:

```json
{
  "device":  {"serial": "9B2428A19448", "manufacturer": "American Power Conversion", "model": "Back-UPS BGM2200-GR"},
  "vars":    {"ups.status": "OL CHRG", "battery.charge": "100", "input.voltage": "229.0"},
  "samples": [{"ts": 1790000000,
               "m":  {"battery.charge": "100", "input.voltage": "229.0", "ups.load": "17"},
               "lo": {"input.voltage": "226.0"},
               "hi": {"input.voltage": "231.0"}}],
  "events":  [{"id": 12, "ts": 1790000000, "kind": "status_change", "old": "OL", "new": "OB DISCHRG", "detail": null}]
}
```

`ts` is a Unix time in UTC. `m` holds the mean of the interval, `lo` and `hi` its minimum and maximum
(both optional). A body without samples and events works as a heartbeat. Answers:
`200 {"status": "ok", "samples": n, "events": n}`, `400` invalid body, `403` bad token, `500` server error.
The endpoint is idempotent: resending a batch inserts nothing twice. Limits per request: 2000 samples, 500 events.

# Raspberry side (`agent/`)

`ups_odoo_push.py` runs next to the existing `upsmon-collector`. It reads the collector SQLite
database read-only and never touches NUT. The standard library is enough.

Store and forward, with flood control:

- SQLite is the buffer. The agent moves two cursors (last sample time, last event id) only after
  Odoo answered `ok`. An Odoo outage loses nothing while the collector keeps its retention (14 days).
- Steady state: one request per `PUSH_INTERVAL` (60 s), which doubles as heartbeat.
- Mains failure: the agent reads the collector live file (tmpfs, once per second). A change of the
  NUT status or a new event goes out at once, at least `PUSH_MIN_GAP` (2 s) after the previous attempt.
- On battery: one request every `PUSH_BATTERY_INTERVAL` (10 s), and the collector writes a sample every 10 s.
- After a failure the wait doubles up to `PUSH_BACKOFF_MAX` (15 min, 60 s on battery) with ±20 % jitter.
- After recovery the backlog drains at one 500-sample batch per second.
- First start backfills `PUSH_BACKFILL_DAYS` (14) of history.

Each sample carries the mean, minimum and maximum of its interval, read from the `samples_range`
table that `collector-minmax.patch` adds. Without the patch the agent falls back to the snapshot
value and sends no min or max.

## Collector patch

The stock collector keeps only the mean of each minute. `collector-minmax.patch` adds the
`samples_range` table (mean, minimum, maximum per flush) and shortens the flush interval to
10 s while the UPS runs on battery. Apply it once, then poll faster so short dips are seen:

```bash
cd / && sudo patch -p1 --backup < /tmp/ups_monitor_agent/collector-minmax.patch
echo 'UPSMON_POLL_INTERVAL=2' | sudo tee -a /etc/upsmon/upsmon.env    # was 10
sudo systemctl restart upsmon-collector upsmon-odoo-push
```

`patch --backup` keeps the original files as `*.orig`.

## Install

```bash
scp -r agent pi@<raspberry>:/tmp/ups_monitor_agent
ssh pi@<raspberry>
cd /tmp/ups_monitor_agent && sudo sh install.sh      # first run creates /etc/upsmon/odoo-push.env
sudo nano /etc/upsmon/odoo-push.env                  # ODOO_URL and ODOO_TOKEN
sudo sh install.sh                                   # installs and starts upsmon-odoo-push.service
journalctl -u upsmon-odoo-push -f
```

## Import the old history

The collector keeps minute snapshots for 30 days and hourly averages for 3 years. The service
sends the snapshots on its own. Older data goes out once, as hourly points, with:

```bash
sudo -u upsmon sh -c 'set -a; . /etc/upsmon/odoo-push.env; python3 /opt/upsmon/ups_odoo_push.py --backfill-hourly'
```

Hourly points stop where the minute snapshots begin, so no hour is counted twice. To resend the
minute snapshots too, stop the service and set `sample_ts` to `0` in `/var/lib/upsmon-push/state.json`.
Odoo skips what it already has.

## Changelog

- 19.0.1.3.0: dashboard accepts a custom date and time range.
- 19.0.1.2.0: dashboard with live tiles, min-max band, outage bands, histogram and statistics;
  per-minute minimum and maximum; immediate push on a status change and every 10 s on battery;
  `collector-minmax.patch`; `ups_monitor.retention_days` default raised to 730.
- 19.0.1.1.0: `--backfill-hourly` imports the hourly history that predates the minute snapshots.
- 19.0.1.0.1: outage lowest charge looks one minute past each edge, so a short self-test no longer reports 0 %.
- 19.0.1.0.0: first release.

# Credits

**Authors:** STeSI Consulting

**Contributors:** Michele Di Croce — dicroce.m@stesi.consulting
