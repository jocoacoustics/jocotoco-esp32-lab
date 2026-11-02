"""Configuración local y serial compartidos; sin interfaz gráfica ni secretos."""

import os
from pathlib import Path
import time
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]


def detect_port():
    configured = os.environ.get("JOCOTOCO_PORT")
    if configured:
        return configured
    ports = [p.device for p in list_ports.comports() if p.vid == 0x10C4 and p.pid == 0xEA60]
    if len(ports) != 1:
        raise RuntimeError("Conecta un único CP210x o define JOCOTOCO_PORT")
    return ports[0]


def read_serial(port, duration):
    until = time.monotonic() + duration
    buf = bytearray()
    while time.monotonic() < until:
        part = port.read(max(port.in_waiting, 1))
        buf.extend(part)
        if b"\x1b[6n" in part or b"\x1b[6n" in buf[-12:]:
            port.write(b"\x1b[1;1R")
        if len(buf) > 250000:
            raise RuntimeError("serial_overflow")
    return buf.decode("utf-8", "replace")
