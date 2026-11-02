"""v0.1.2. Diagnóstico serial de lectura; no muestra SSID ni secretos."""

import json
import re
import serial
from lab_common import ROOT, read_serial, detect_port

p = serial.Serial(port=None, baudrate=115200, timeout=0.1)
p.dtr = False
p.rts = False
p.port = detect_port()
try:
    p.open()
    p.write(b"\r\n")
    read_serial(p, 2)
    p.write(b"show status\r\n")
    status = read_serial(p, 3)
    p.write(b"show config\r\n")
    config = read_serial(p, 3)
    p.write(b"scan\r\n")
    scan = read_serial(p, 15)
    clean = lambda s: re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", s)
    config, scan = clean(config), clean(scan)
    match = re.search(r"STA Settings:.*?SSID:\s*([^\r\n]+)", config, re.S)
    ssid = match.group(1).strip() if match else None
    ip = re.search(r"Uplink IP:\s*(\d+\.\d+\.\d+\.\d+)", status)
    count = re.search(r"Found (\d+) networks:", scan)
    output = dict(
        console_responds="Router Status:" in status,
        configured_ssid_read=bool(ssid and ssid != "<undef>"),
        networks_found=int(count.group(1)) if count else None,
        scan_failed="Scan failed:" in scan,
        uplink_has_ip=bool(ip and ip.group(1) != "0.0.0.0"),
        configured_ssid_detected_in_scan=bool(ssid and ssid in scan),
        scan_responds=("SSID" in scan or "scan" in scan.lower()),
        ap_enabled="AP interface: enabled" in status,
        clients=(
            int(re.search(r"Connected clients:\s*(\d+)", status).group(1))
            if re.search(r"Connected clients:\s*(\d+)", status)
            else None
        ),
    )
    # Solo metadatos sin SSID, claves ni respuestas crudas.
    (ROOT / "resultados").mkdir(parents=True, exist_ok=True)
    (ROOT / "resultados" / "diagnostico-v0.1.2.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(json.dumps(output, indent=2))
finally:
    p.close()
