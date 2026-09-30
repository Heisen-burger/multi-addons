#!/usr/bin/env python3
"""Push the upsmon SQLite data to Odoo (module ups_monitor).

Store and forward: the collector already writes every sample and event to
SQLite, so that file is the buffer. This agent keeps two cursors (last sample
timestamp, last event id) and advances them only after Odoo answered "ok".
An unreachable Odoo loses nothing; the backlog goes out in batches once it
answers again.

Flood control:
- steady state: one POST per PUSH_INTERVAL (also serves as heartbeat);
- a new event (mains failure) goes out at once, but never sooner than
  MIN_GAP seconds after the previous attempt;
- after a failure the delay doubles up to BACKOFF_MAX, with +-20% jitter;
- a backlog drains at one batch per second.

Standard library only.
"""
import json
import logging
import os
import random
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request

LOG = logging.getLogger("upsmon.push")

URL = os.environ["ODOO_URL"].rstrip("/") + "/ups_monitor/ingest"
TOKEN = os.environ["ODOO_TOKEN"]
DB = os.environ.get("UPSMON_DB", "/var/lib/upsmon/upsmon.db")
LIVE = os.environ.get("UPSMON_LIVE", "/run/upsmon/latest.json")
STATE = os.environ.get("PUSH_STATE", "/var/lib/upsmon-push/state.json")
PUSH_INTERVAL = int(os.environ.get("PUSH_INTERVAL", "60"))
MIN_GAP = int(os.environ.get("PUSH_MIN_GAP", "10"))
BACKOFF_MAX = int(os.environ.get("PUSH_BACKOFF_MAX", "900"))
BATCH = int(os.environ.get("PUSH_BATCH", "500"))
BACKFILL_DAYS = int(os.environ.get("PUSH_BACKFILL_DAYS", "14"))
TIMEOUT = int(os.environ.get("PUSH_TIMEOUT", "20"))
TICK = 5

# NUT variables Odoo stores as time series; keep in sync with ups_monitor/models/ups_sample.py
KEEP = ("battery.charge", "battery.runtime", "battery.voltage", "input.voltage", "ups.load")

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def load_state():
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"sample_ts": int(time.time()) - BACKFILL_DAYS * 86400, "event_id": 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE)  # atomic: a crash never leaves half a file


def open_db():
    # read-only: the collector stays the only writer
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def live_vars(con):
    """Current NUT variables: the live file, else the newest stored snapshot."""
    try:
        with open(LIVE) as fh:
            live = json.load(fh)
        if live.get("online") and live.get("vars"):
            return live["vars"]
    except (OSError, ValueError):
        pass
    row = con.execute("SELECT data FROM snapshots ORDER BY ts DESC LIMIT 1").fetchone()
    return json.loads(row["data"]) if row else {}


def build_batch(con, state, current):
    ts_rows = con.execute(
        "SELECT ts, data FROM snapshots WHERE ts > ? ORDER BY ts LIMIT ?",
        (state["sample_ts"], BATCH)).fetchall()
    samples = []
    for row in ts_rows:
        data = json.loads(row["data"])
        samples.append({"ts": row["ts"], "m": {k: data[k] for k in KEEP if k in data}})
    events = [dict(r) for r in con.execute(
        "SELECT id, ts, kind, old, new, detail FROM events WHERE id > ? ORDER BY id LIMIT ?",
        (state["event_id"], BATCH))]
    serial = current.get("device.serial") or current.get("ups.serial") or state.get("serial")
    if not serial:
        raise RuntimeError("UPS serial unknown yet")
    state["serial"] = serial
    return {
        "device": {
            "serial": serial,
            "manufacturer": current.get("device.mfr") or current.get("ups.mfr"),
            "model": (current.get("device.model") or current.get("ups.model") or "").strip(),
        },
        "vars": current,
        "samples": samples,
        "events": events,
    }


def post(payload):
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Auth-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.load(resp)
    if body.get("status") != "ok":
        raise RuntimeError(f"Odoo answered {body}")
    return body


def push_all(state):
    """Send batches until no backlog is left. Raises on the first failure; cursors stay put."""
    while _running:
        con = open_db()
        try:
            payload = build_batch(con, state, live_vars(con))
        finally:
            con.close()
        post(payload)
        if payload["samples"]:
            state["sample_ts"] = payload["samples"][-1]["ts"]
        if payload["events"]:
            state["event_id"] = payload["events"][-1]["id"]
        save_state(state)
        LOG.info("sent %d samples, %d events", len(payload["samples"]), len(payload["events"]))
        if len(payload["samples"]) < BATCH and len(payload["events"]) < BATCH:
            return
        time.sleep(1)


def newest_event_id():
    con = open_db()
    try:
        return con.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
    finally:
        con.close()


def main():
    logging.basicConfig(level=os.environ.get("PUSH_LOGLEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    state = load_state()
    last_attempt = 0.0
    next_try = 0.0
    failures = 0
    LOG.info("started, target %s, interval %ss", URL, PUSH_INTERVAL)
    while _running:
        now = time.time()
        try:
            new_event = newest_event_id() > state["event_id"]
        except sqlite3.Error as exc:
            LOG.warning("SQLite not readable: %s", exc)
            new_event = False
        if now >= next_try and now - last_attempt >= MIN_GAP and (
                new_event or now - last_attempt >= PUSH_INTERVAL):
            last_attempt = now
            try:
                push_all(state)
                if failures:
                    LOG.info("Odoo reachable again after %d failed attempts", failures)
                failures = 0
                next_try = 0.0
            except (urllib.error.URLError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                failures += 1
                delay = min(PUSH_INTERVAL * 2 ** failures, BACKOFF_MAX) * random.uniform(0.8, 1.2)
                next_try = time.time() + delay
                LOG.warning("push failed (%s); retry in %ds, data stays queued in SQLite", exc, delay)
        time.sleep(TICK)
    LOG.info("stopped")


if __name__ == "__main__":
    sys.exit(main())
