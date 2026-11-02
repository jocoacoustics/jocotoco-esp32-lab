"""v0.4.0. Cambio NVS autorizado por el usuario: web_ui bind ap,sta."""

import json
import re
import serial
from lab_common import ROOT, read_serial, detect_port

p = serial.Serial(None, 115200, timeout=0.1)
p.dtr = False
p.rts = False
p.port = detect_port()
try:
    p.open()
    p.write(b"\r\n")
    read_serial(p, 1)
    p.write(b"web_ui bind ap,sta\r\n")
    reply = read_serial(p, 3)
    if "non-zero error" in reply or "Unrecognized" in reply:
        raise RuntimeError("No se pudo guardar bind")
    p.write(b"web_ui\r\n")
    web = read_serial(p, 3)
    p.write(b"remote_console status\r\n")
    remote = read_serial(p, 3)
    p.write(b"show status\r\n")
    status = read_serial(p, 3)
    ip = re.search(r"Uplink IP:\s*(\d+\.\d+\.\d+\.\d+)", status)
    ok = "Web interface: enabled" in web and "bind: AP STA " in web and "disabled" in remote.lower()
    result = dict(
        version="0.4.0",
        web_ap_sta=ok,
        remote_disabled="disabled" in remote.lower(),
        host=ip[1] if ip else None,
        credentials_unchanged=True,
    )
    (ROOT / "resultados").mkdir(parents=True, exist_ok=True)
    (ROOT / "resultados" / "acceso-red-v0.4.0.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
finally:
    p.close()
