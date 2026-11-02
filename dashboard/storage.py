"""SQLite local v0.3.0. Tiempos UTC del PC en ms; presentación America/Guayaquil."""

from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

DB = Path(__file__).resolve().parents[1] / "data" / "jocotoco_wifi.sqlite3"
SESSION = uuid.uuid4().hex


@contextmanager
def connect():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def init():
    with connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(
            """
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,started_ms INTEGER NOT NULL,clock TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,session TEXT NOT NULL,started_ms INTEGER NOT NULL,t_ms INTEGER NOT NULL,rssi INTEGER,channel INTEGER,clients INTEGER,sent INTEGER,received INTEGER,down REAL,up REAL,uptime TEXT);
        CREATE INDEX IF NOT EXISTS sample_time ON samples(t_ms);
        CREATE TABLE IF NOT EXISTS client_observations(id INTEGER PRIMARY KEY,sample_id INTEGER NOT NULL REFERENCES samples(id),client_id TEXT,ip TEXT,name TEXT);
        CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY,session TEXT NOT NULL,started_ms INTEGER NOT NULL,t_ms INTEGER NOT NULL,duration_ms INTEGER NOT NULL,status TEXT NOT NULL,observations INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS scan_time ON scans(t_ms);
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,scan_id INTEGER NOT NULL REFERENCES scans(id),identity TEXT NOT NULL,ssid TEXT NOT NULL,channel INTEGER NOT NULL,security TEXT NOT NULL,rssi INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS observation_identity ON observations(identity,scan_id);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,t_ms INTEGER NOT NULL,session TEXT NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_metrics(id INTEGER PRIMARY KEY,t_ms INTEGER NOT NULL,session TEXT NOT NULL,cpu REAL,core0 REAL,core1 REAL,heap_free INTEGER,heap_used INTEGER,heap_total INTEGER,image_bytes INTEGER,slot_bytes INTEGER,payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS device_metrics_time ON device_metrics(t_ms);
        PRAGMA user_version=6;
        """
        )
        for table, column, definition in [
            ("samples", "source", "TEXT NOT NULL DEFAULT 'usb'"),
            ("samples", "counter_precision", "TEXT NOT NULL DEFAULT 'exact'"),
            ("scans", "source", "TEXT NOT NULL DEFAULT 'usb'"),
        ]:
            columns = {r[1] for r in con.execute("PRAGMA table_info(" + table + ")")}
            if column not in columns:
                con.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition)
        con.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (
                SESSION,
                round(time.time() * 1000),
                "PC UTC epoch milliseconds; display America/Guayaquil; NTP unverified",
            ),
        )


def identity(row):
    return json.dumps(
        [row["ssid"], row["channel"], row["security"]], ensure_ascii=False, separators=(",", ":")
    )


def sample(started, now, status, tx, rx, down, up, source="usb", counter_precision="exact"):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO samples(session,started_ms,t_ms,rssi,channel,clients,sent,received,down,up,uptime) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                SESSION,
                round(started * 1000),
                round(now * 1000),
                status["rssi"],
                status["channel"],
                status["client_count"],
                tx,
                rx,
                down,
                up,
                status["uptime"],
            ),
        )
        con.executemany(
            "INSERT INTO client_observations(sample_id,client_id,ip,name) VALUES(?,?,?,?)",
            [(cur.lastrowid, c["id"], c["ip"], c["name"]) for c in status.get("clients", [])],
        )
        con.execute(
            "UPDATE samples SET source=?,counter_precision=? WHERE id=?",
            (source, counter_precision, cur.lastrowid),
        )


def scan(started, ended, rows, ok, source="usb"):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO scans(session,started_ms,t_ms,duration_ms,status,observations) VALUES(?,?,?,?,?,?)",
            (
                SESSION,
                round(started * 1000),
                round(ended * 1000),
                round((ended - started) * 1000),
                "ok" if ok else "error",
                len(rows),
            ),
        )
        con.executemany(
            "INSERT INTO observations(scan_id,identity,ssid,channel,security,rssi) VALUES(?,?,?,?,?,?)",
            [
                (cur.lastrowid, identity(r), r["ssid"], r["channel"], r["security"], r["rssi"])
                for r in rows
            ],
        )
        con.execute("UPDATE scans SET source=? WHERE id=?", (source, cur.lastrowid))


def event(kind, detail):
    with connect() as con:
        con.execute(
            "INSERT INTO events(t_ms,session,kind,detail) VALUES(?,?,?,?)",
            (round(time.time() * 1000), SESSION, kind, detail),
        )


def metrics(now, data):
    cpu = data["cpu"]
    heap = data["heap"]
    flash = data["flash"]
    with connect() as con:
        con.execute(
            "INSERT INTO device_metrics(t_ms,session,cpu,core0,core1,heap_free,heap_used,heap_total,image_bytes,slot_bytes,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                round(now * 1000),
                SESSION,
                cpu.get("used_percent") if cpu.get("valid") else None,
                cpu.get("core0_percent") if cpu.get("valid") else None,
                cpu.get("core1_percent") if cpu.get("valid") else None,
                heap["free_bytes"],
                heap["used_bytes"],
                heap["total_bytes"],
                flash.get("active_image_bytes"),
                flash.get("active_slot_bytes"),
                json.dumps(data),
            ),
        )


def history(minutes=60):
    since = round((time.time() - minutes * 60) * 1000)
    with connect() as con:
        total = con.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        total_scans = con.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        # 2000 latest samples; not silently presenting them as a full large-range history.
        raw = con.execute(
            "SELECT * FROM samples WHERE t_ms>=? ORDER BY t_ms DESC LIMIT 2000", (since,)
        ).fetchall()[::-1]
        samples = [
            dict(
                t=r["t_ms"] / 1000,
                rssi=r["rssi"],
                down=r["down"],
                up=r["up"],
                clients=r["clients"],
                source=r["source"],
                counter_precision=r["counter_precision"],
            )
            for r in raw
        ]
        scans = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM scans WHERE t_ms>=? ORDER BY t_ms DESC LIMIT 2000", (since,)
            ).fetchall()[::-1]
        ]
        rows = con.execute(
            """SELECT o.*,s.t_ms FROM observations o JOIN scans s ON s.id=o.scan_id
                            WHERE s.t_ms>=? ORDER BY s.t_ms,o.id""",
            (since,),
        ).fetchall()
        groups = {}
        for r in rows:
            key = r["identity"]
            if key not in groups:
                groups[key] = dict(
                    key=key, ssid=r["ssid"], channel=r["channel"], security=r["security"], points=[]
                )
            points = groups[key]["points"]
            # Duplicate SSID/channel observations in one scan are distinct raw DB rows;
            # graph uses strongest RSSI and labels identity ambiguity.
            if points and points[-1]["scan_id"] == r["scan_id"]:
                points[-1]["rssi"] = max(points[-1]["rssi"], r["rssi"])
                points[-1]["duplicates"] += 1
            else:
                points.append(
                    dict(t=r["t_ms"] / 1000, rssi=r["rssi"], scan_id=r["scan_id"], duplicates=1)
                )
        networks = sorted(groups.values(), key=lambda g: g["points"][-1]["rssi"], reverse=True)
        for g in networks:
            p = g["points"]
            g.update(
                last=p[-1]["rssi"],
                delta=p[-1]["rssi"] - p[-2]["rssi"] if len(p) > 1 else None,
                minimum=min(x["rssi"] for x in p),
                maximum=max(x["rssi"] for x in p),
                count=len(p),
            )
        events = [
            dict(r)
            for r in con.execute(
                "SELECT t_ms,kind,detail FROM events WHERE t_ms>=? ORDER BY t_ms DESC LIMIT 100",
                (since,),
            )
        ]
        metrics_rows = [
            dict(r)
            for r in con.execute(
                "SELECT t_ms,cpu,core0,core1,heap_free,heap_used,heap_total FROM device_metrics WHERE t_ms>=? ORDER BY t_ms DESC LIMIT 2000",
                (since,),
            ).fetchall()[::-1]
        ]
        return dict(
            samples=samples,
            scans=scans,
            networks=networks,
            events=events,
            device_metrics=metrics_rows,
            total_samples=total,
            total_scans=total_scans,
            database_bytes=DB.stat().st_size,
            minutes=minutes,
            clock="PC · America/Guayaquil · NTP no verificado",
            truncated=len(samples) == 2000 or len(scans) == 2000,
            session=SESSION,
        )


def export_json():
    # Complete authorized local data export. No credentials exist in this database.
    with connect() as con:
        return {
            name: [dict(r) for r in con.execute("SELECT * FROM " + name)]
            for name in (
                "sessions",
                "samples",
                "client_observations",
                "scans",
                "observations",
                "events",
                "device_metrics",
            )
        }
