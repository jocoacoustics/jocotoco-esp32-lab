"""v0.4.0. Lee páginas de estado públicas del firmware; no envía credenciales."""

from html.parser import HTMLParser
import ipaddress
import re
import json
import math
import time
import urllib.request
from urllib.parse import urlparse


def validate_host(host):
    ip = ipaddress.ip_address(host)
    if ip.version != 4 or not any(
        ip in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ):
        raise ValueError("Se requiere una IP privada de la red local")
    return str(ip)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Redirección no permitida")


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_status(html):
    table = Tables()
    table.feed(html)
    rows = {r[0].rstrip(":"): r[1] for r in table.rows if len(r) == 2}
    if "Uplink" not in rows or rows.get("SSID") != "Jocotoco-Lab":
        raise ValueError("No es el estado de Jocotoco-Lab")
    rssi = re.search(r"(-?\d+) dBm", rows["Uplink"])
    counts = re.search(
        r"([\d.]+)\s*(B|KB|MB|GB)\s+sent\s*/\s*([\d.]+)\s*(B|KB|MB|GB)\s+received",
        rows.get("Bytes", ""),
    )

    def amount(value, unit):
        return round(float(value) * 1024 ** ("B", "KB", "MB", "GB").index(unit))

    tx = amount(counts[1], counts[2]) if counts else None
    rx = amount(counts[3], counts[4]) if counts else None
    ip = rows.get("STA IP")
    status = dict(
        rssi=int(rssi[1]) if rssi else None,
        channel=None,
        uplink_ip=ip if ip and ip != "N/A" else None,
        client_count=int(rows.get("AP Clients", 0)),
        uptime=rows.get("Uptime"),
        ap_enabled="AP IP" in rows,
        clients=[],
    )
    return status, tx, rx


def parse_scan(html):
    table = Tables()
    table.feed(html)
    rows = []
    for row in table.rows:
        if len(row) < 4:
            continue
        rssi = re.search(r"(-?\d+) dBm", row[1])
        channel = re.match(r"^(\d+)", row[2])
        if rssi and channel:
            rows.append(
                dict(
                    ssid=row[0] or "(Red oculta)",
                    channel=int(channel[1]),
                    rssi=int(rssi[1]),
                    security=row[3],
                )
            )
    valid = bool(rows) or "No networks found" in html
    return sorted(rows, key=lambda r: -r["rssi"]), valid


class Client:
    def __init__(self, host):
        self.host = validate_host(host)
        self.url = "http://" + self.host
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path):
        if path not in ("/", "/scan", "/api/lab/metrics"):
            raise ValueError("Ruta no permitida")
        req = urllib.request.Request(
            self.url + path,
            headers={"User-Agent": "Jocotoco-Lab/0.4.0", "Cache-Control": "no-cache"},
        )
        with self.opener.open(req, timeout=8) as response:
            data = response.read(400000)
        return data.decode("utf-8", "replace")

    def poll(self):
        return parse_status(self.get("/"))

    def metrics(self):
        data = json.loads(self.get("/api/lab/metrics"))
        if data.get("schema") != 1 or not all(
            isinstance(data.get(k), dict) for k in ("cpu", "heap", "flash")
        ):
            raise ValueError("Esquema de telemetría inválido")
        heap = data["heap"]
        for key in ("free_bytes", "used_bytes", "total_bytes"):
            if (
                not isinstance(heap.get(key), (int, float))
                or not math.isfinite(heap[key])
                or heap[key] < 0
            ):
                raise ValueError("Heap inválido")
        if heap["free_bytes"] + heap["used_bytes"] != heap["total_bytes"]:
            raise ValueError("Heap inconsistente")
        if data["cpu"].get("valid"):
            for key in ("used_percent", "core0_percent", "core1_percent"):
                value = data["cpu"].get(key)
                if (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 100
                ):
                    raise ValueError("CPU inválida")
        return data

    def scan(self):
        # Firmware serves previous scan, then starts a new asynchronous scan.
        # Discard first cached result and retrieve after an acquisition window.
        self.get("/scan")
        time.sleep(3)
        return parse_scan(self.get("/scan"))
