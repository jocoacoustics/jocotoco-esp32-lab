"""Jocotoco Lab v0.2.0 — telemetría USB, solo lectura, servidor loopback."""

import copy
import json
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs
import storage
from http_transport import Client, validate_host
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import serial
from serial.tools import list_ports

BASE = Path(__file__).resolve().parent
LOCK = threading.Lock()
SCAN = threading.Event()
PAUSE = threading.Event()
STATE = dict(
    version="0.3.0",
    connected=False,
    message="Buscando ESP32 por USB",
    samples=[],
    networks=[],
    clients=[],
    scanning=False,
    paused=False,
    scan_interval=60,
)
LINK_FILE = BASE.parent / "resultados" / "acceso-red-v0.4.0.json"
try:
    link = json.loads(LINK_FILE.read_text(encoding="utf-8"))
    if link.get("web_ap_sta"):
        STATE.update(transport="http", http_host=validate_host(link["host"]), version="0.4.0")
except (OSError, ValueError, KeyError):
    pass
STATE.setdefault("transport", "usb")
STATE.setdefault("http_host", None)
STATE["version"] = "0.6.0"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def command(port, cmd, timeout=4):
    # Lista cerrada: nunca aceptar comandos del navegador.
    assert cmd in ("show status", "bytes", "scan", "web_ui", "remote_console status")
    port.reset_input_buffer()
    port.write((cmd + "\r\n").encode())
    buf = bytearray()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        buf.extend(port.read(max(1, port.in_waiting)))
        if b"\x1b[6n" in buf[-20:]:
            port.write(b"\x1b[1;1R")
        marker = {
            "show status": b"Router Status:",
            "bytes": b"Received:",
            "scan": b"networks",
            "web_ui": b"Web interface:",
            "remote_console status": b"console",
        }[cmd]
        if marker in buf and buf.rfind(b"esp32>") > buf.find(marker):
            break
        if len(buf) > 200000:
            raise RuntimeError("Respuesta serial excesiva")
    return ANSI.sub("", buf.decode("utf-8", "replace"))


def parse_status(text):
    def find(pattern, cast=str):
        m = re.search(pattern, text)
        return cast(m.group(1)) if m else None

    clients = []
    for line in text.splitlines():
        m = re.match(r"([0-9A-Fa-f:]{17})\s+(\d+\.\d+\.\d+\.\d+|N/A)\s*(.*)", line)
        if m:
            clients.append(dict(id="••:" + m[1][-5:], ip=m[2], name=m[3].strip() or "Sin nombre"))
    return dict(
        rssi=find(r"connected \(ch \d+, (-?\d+) dBm\)", int),
        channel=find(r"connected \(ch (\d+)", int),
        uplink_ip=find(r"Uplink IP:\s*(\d+\.\d+\.\d+\.\d+)"),
        client_count=find(r"Connected clients:\s*(\d+)", int),
        uptime=find(r"Uptime:\s*([^\r\n]+)"),
        clients=clients,
        ap_enabled="AP interface: enabled" in text,
    )


def parse_scan(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"^(.{32})\s+(\d+)\s+(-?\d+)\s+(.+?)\s*$", line)
        if m:
            rows.append(
                dict(
                    ssid=m[1].strip() or "(Red oculta)",
                    channel=int(m[2]),
                    rssi=int(m[3]),
                    security=m[4],
                )
            )
    return sorted(rows, key=lambda n: -n["rssi"])


def network_collector():
    prev = None
    next_scan = time.monotonic() + 4
    last_host = None
    next_metrics = 0
    while STATE.get("transport") == "http":
        try:
            if PAUSE.is_set():
                with LOCK:
                    STATE["paused"] = True
                time.sleep(0.5)
                continue
            host = STATE["http_host"]
            if host != last_host:
                client = Client(host)
                prev = None
                last_host = host
                storage.event(
                    "transport_http",
                    "Lectura por red doméstica; contadores redondeados; sin credenciales.",
                )
            started = time.time()
            status, tx, rx = client.poll()
            now = time.time()
            mono = time.monotonic()
            down = up = None
            if prev and tx is not None and rx is not None and tx >= prev[1] and rx >= prev[2]:
                dt = mono - prev[0]
                up = (tx - prev[1]) * 8 / dt / 1e6
                down = (rx - prev[2]) * 8 / dt / 1e6
            prev = (mono, tx, rx) if tx is not None and rx is not None else None
            storage.sample(started, now, status, tx, rx, down, up, "http", "rounded")
            if time.monotonic() >= next_metrics:
                try:
                    metrics = client.metrics()
                    storage.metrics(time.time(), metrics)
                    with LOCK:
                        STATE.update(device_metrics=metrics, metrics_updated=time.time())
                    next_metrics = time.monotonic() + 3
                except Exception:
                    next_metrics = time.monotonic() + 30
            with LOCK:
                STATE.update(
                    status,
                    connected=True,
                    paused=False,
                    message="Lectura HTTP activa · sin USB",
                    updated=now,
                    sent=tx,
                    received=rx,
                    down_mbps=down,
                    up_mbps=up,
                    port="Wi-Fi · " + host,
                    web_disabled=False,
                    web_ap_only=False,
                    web_ap_sta=True,
                    remote_disabled=True,
                    security_verified=False,
                    counter_precision="rounded",
                    clients_detail_available=False,
                )
                STATE["samples"].append(dict(t=now, rssi=status["rssi"], down=down, up=up))
                STATE["samples"] = STATE["samples"][-360:]
                interval = STATE["scan_interval"]
            if SCAN.is_set() or (interval and time.monotonic() >= next_scan):
                SCAN.clear()
                with LOCK:
                    STATE["scanning"] = True
                scan_started = time.time()
                rows, ok = client.scan()
                scan_ended = time.time()
                storage.scan(scan_started, scan_ended, rows, ok, "http")
                with LOCK:
                    STATE.update(networks=rows, scan_time=scan_ended, scanning=False, scan_ok=ok)
                next_scan = time.monotonic() + max(30, interval)
            time.sleep(3)
        except Exception:
            prev = None
            if STATE["connected"]:
                storage.event(
                    "http_disconnected",
                    "Sin respuesta de la IP local del ESP32; no rellenar huecos.",
                )
            with LOCK:
                STATE.update(
                    connected=False,
                    scanning=False,
                    message="ESP32 sin respuesta por HTTP. Revisa alimentación, alcance e IP doméstica.",
                )
            time.sleep(3)


def collector():
    prev = None
    next_scan = time.monotonic() + 10
    while True:
        if STATE.get("transport") == "http":
            network_collector()
            continue
        port = None
        try:
            devices = [
                p.device for p in list_ports.comports() if p.vid == 0x10C4 and p.pid == 0xEA60
            ]
            if len(devices) != 1:
                raise RuntimeError("Conecta un único ESP32 CP210x por USB")
            port = serial.Serial(None, 115200, timeout=0.1)
            port.dtr = False
            port.rts = False
            port.port = devices[0]
            port.open()
            port.write(b"\r\n")
            time.sleep(0.3)
            web = command(port, "web_ui")
            remote = command(port, "remote_console status")
            with LOCK:
                STATE.update(
                    port=devices[0],
                    web_disabled="Web interface: disabled" in web,
                    web_ap_only="Web interface: enabled" in web and "bind: AP " in web,
                    remote_disabled="disabled" in remote.lower(),
                )
            while True:
                if STATE.get("transport") == "http":
                    break
                if PAUSE.is_set():
                    with LOCK:
                        STATE["paused"] = True
                    time.sleep(0.5)
                    continue
                started = time.time()
                mono_started = time.monotonic()
                status = parse_status(command(port, "show status"))
                if status["client_count"] is None:
                    raise RuntimeError("Sin respuesta válida de la consola USB")
                counts = command(port, "bytes")
                sent = re.search(r"Sent:\s*(\d+) bytes", counts)
                received = re.search(r"Received:\s*(\d+) bytes", counts)
                now = time.time()
                tx, rx = int(sent[1]) if sent else None, int(received[1]) if received else None
                down = up = None
                if prev and tx is not None and rx is not None and tx >= prev[1] and rx >= prev[2]:
                    dt = time.monotonic() - prev[0]
                    up, down = (tx - prev[1]) * 8 / dt / 1e6, (rx - prev[2]) * 8 / dt / 1e6
                prev = (time.monotonic(), tx, rx) if tx is not None and rx is not None else None
                storage.sample(started, now, status, tx, rx, down, up)
                with LOCK:
                    STATE.update(
                        status,
                        connected=True,
                        paused=False,
                        message="Lectura USB activa",
                        updated=now,
                        sent=tx,
                        received=rx,
                        down_mbps=down,
                        up_mbps=up,
                    )
                    STATE["samples"].append(dict(t=now, rssi=status["rssi"], down=down, up=up))
                    STATE["samples"] = STATE["samples"][-360:]
                with LOCK:
                    interval = STATE["scan_interval"]
                if SCAN.is_set() or (interval and time.monotonic() >= next_scan):
                    SCAN.clear()
                    with LOCK:
                        STATE["scanning"] = True
                    scan_started = time.time()
                    raw_scan = command(port, "scan", 18)
                    rows = parse_scan(raw_scan)
                    scan_ended = time.time()
                    ok = (
                        "Found " in raw_scan or "No networks found." in raw_scan
                    ) and "Scan failed:" not in raw_scan
                    storage.scan(scan_started, scan_ended, rows, ok)
                    next_scan = time.monotonic() + max(interval, 30)
                    with LOCK:
                        STATE.update(
                            networks=rows, scan_time=scan_ended, scanning=False, scan_ok=ok
                        )
                time.sleep(2)
        except Exception:
            prev = None
            if STATE["connected"]:
                storage.event(
                    "usb_disconnected", "Sin respuesta USB; no se rellenan huecos con ceros."
                )
            with LOCK:
                STATE.update(
                    connected=False,
                    message="USB no disponible. Revisa cable, puerto u otra consola abierta.",
                    scanning=False,
                )
            time.sleep(3)
        finally:
            if port:
                port.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/hardware":
            report = BASE.parent / "resultados" / "ota-preflight-v0.5.0.json"
            try:
                preflight = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                preflight = None
            with LOCK:
                metrics = copy.deepcopy(STATE.get("device_metrics"))
                updated = STATE.get("metrics_updated")
            self.send(
                json.dumps(
                    dict(
                        flash_capacity_bytes=4194304,
                        ota_slot_bytes=1572864,
                        metrics=metrics,
                        metrics_updated=updated,
                        voltage=None,
                        preflight=preflight,
                    )
                ).encode()
            )
        elif parsed.path == "/api/history":
            try:
                minutes = int(parse_qs(parsed.query).get("minutes", ["60"])[0])
                if minutes not in (5, 15, 60, 360, 1440):
                    raise ValueError()
                self.send(json.dumps(storage.history(minutes)).encode())
            except ValueError:
                self.send(b"{}", status=400)
        elif parsed.path == "/api/export":
            self.send(json.dumps(storage.export_json()).encode())
        elif self.path == "/api/state":
            with LOCK:
                snapshot = copy.deepcopy(STATE)
            self.send(json.dumps(snapshot).encode())
        elif self.path in ("/", "/index.html"):
            self.send((BASE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/main.js":
            self.send((BASE / "main.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/styles.css":
            self.send((BASE / "styles.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/history.js":
            self.send((BASE / "history.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/network.js":
            self.send((BASE / "network.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/hardware.js":
            self.send((BASE / "hardware.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/health.js":
            self.send((BASE / "health.js").read_bytes(), "text/javascript; charset=utf-8")
        else:
            self.send(b"{}", status=404)

    def do_POST(self):
        if self.headers.get("Origin") != "http://127.0.0.1:8785":
            return self.send(b"{}", status=403)
        if self.path == "/api/network":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 200:
                    raise ValueError()
                host = validate_host(json.loads(self.rfile.read(length))["host"])
                with LOCK:
                    STATE.update(transport="http", http_host=host, connected=False)
                LINK_FILE.parent.mkdir(parents=True, exist_ok=True)
                LINK_FILE.write_text(
                    json.dumps(dict(version="0.4.0", host=host, web_ap_sta=True)), encoding="utf-8"
                )
            except (ValueError, KeyError, TypeError):
                return self.send(b"{}", status=400)
        elif self.path == "/api/mark":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 1200:
                    raise ValueError()
                detail = json.loads(self.rfile.read(length))["detail"]
                if not isinstance(detail, str) or not 1 <= len(detail) <= 200:
                    raise ValueError()
                storage.event("anotacion_manual", detail)
            except (ValueError, KeyError, TypeError):
                return self.send(b"{}", status=400)
        elif self.path == "/api/interval":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 200:
                    raise ValueError()
                interval = json.loads(self.rfile.read(length))["seconds"]
                if interval not in (0, 30, 60, 120, 300):
                    raise ValueError()
                with LOCK:
                    STATE["scan_interval"] = interval
                storage.event("scan_interval", str(interval) + " segundos; 0=manual")
            except (ValueError, KeyError, TypeError):
                return self.send(b"{}", status=400)
        elif self.path == "/api/scan":
            SCAN.set()
        elif self.path == "/api/pause":
            PAUSE.clear() if PAUSE.is_set() else PAUSE.set()
        else:
            return self.send(b"{}", status=404)
        self.send(b'{"ok":true}')


if __name__ == "__main__":
    storage.init()
    threading.Thread(target=collector, daemon=True).start()
    print("Jocotoco Lab: http://127.0.0.1:8785", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8785), Handler).serve_forever()
