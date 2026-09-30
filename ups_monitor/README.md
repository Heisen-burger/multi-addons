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
| UPS Monitor > UPS | One card per UPS: status, battery, load, mains voltage, agent state. Chatter receives the alerts. |
| UPS Monitor > Charts | Mains voltage, battery charge and load over time (graph, pivot, list; last 24 h by default). |
| UPS Monitor > Mains outages | One record per outage: start, end, duration, lowest battery charge, low-battery flag. Bar graph per month. |
| UPS Monitor > Events | Status changes and UPS communication losses reported by the collector. |

An outage opens when the NUT status contains `OB` (on battery) and closes when `OB` disappears.
A status such as `OL DISCHRG` (self-test on mains) is not an outage.

## Models

| Model | Purpose |
|---|---|
| `ups.device` | One UPS, keyed by serial number. Latest values, agent state, chatter. Created on first contact. |
| `ups.sample` | One row per minute: battery charge, runtime, battery voltage, input voltage, load. Unique per (device, timestamp). |
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
| `ups_monitor.retention_days` | 90 | Samples older than this are purged daily. Events and outages stay. |

Add the users who should receive alerts as followers of the UPS.

## Endpoint

`POST /ups_monitor/ingest`, header `X-Auth-Token`, flat JSON body:

```json
{
  "device":  {"serial": "9B2428A19448", "manufacturer": "American Power Conversion", "model": "Back-UPS BGM2200-GR"},
  "vars":    {"ups.status": "OL CHRG", "battery.charge": "100", "input.voltage": "229.0"},
  "samples": [{"ts": 1790000000, "m": {"battery.charge": "100", "input.voltage": "229.0", "ups.load": "17"}}],
  "events":  [{"id": 12, "ts": 1790000000, "kind": "status_change", "old": "OL", "new": "OB DISCHRG", "detail": null}]
}
```

`ts` is a Unix time in UTC. A body without samples and events works as a heartbeat. Answers:
`200 {"status": "ok", "samples": n, "events": n}`, `400` invalid body, `403` bad token, `500` server error.
The endpoint is idempotent: resending a batch inserts nothing twice. Limits per request: 2000 samples, 500 events.

# Raspberry side (`agent/`)

`ups_odoo_push.py` runs next to the existing `upsmon-collector`. It reads the collector SQLite
database read-only and never touches NUT. The standard library is enough.

Store and forward, with flood control:

- SQLite is the buffer. The agent moves two cursors (last sample time, last event id) only after
  Odoo answered `ok`. An Odoo outage loses nothing while the collector keeps its retention (14 days).
- Steady state: one request per `PUSH_INTERVAL` (60 s), which doubles as heartbeat.
- A new event (mains failure) goes out at once, but at least `PUSH_MIN_GAP` (10 s) after the previous attempt.
- After a failure the wait doubles up to `PUSH_BACKOFF_MAX` (15 min) with ±20 % jitter.
- After recovery the backlog drains at one 500-sample batch per second.
- First start backfills `PUSH_BACKFILL_DAYS` (14) of history.

Samples come from the collector `snapshots` table, so each minute carries the instantaneous value
of the last poll, not the one-minute mean.

## Install

```bash
scp -r agent pi@<raspberry>:/tmp/ups_monitor_agent
ssh pi@<raspberry>
cd /tmp/ups_monitor_agent && sudo sh install.sh      # first run creates /etc/upsmon/odoo-push.env
sudo nano /etc/upsmon/odoo-push.env                  # ODOO_URL and ODOO_TOKEN
sudo sh install.sh                                   # installs and starts upsmon-odoo-push.service
journalctl -u upsmon-odoo-push -f
```

## Changelog

- 19.0.1.0.0: first release.

# Credits

**Authors:** STeSI Consulting

**Contributors:** Michele Di Croce — dicroce.m@stesi.consulting
