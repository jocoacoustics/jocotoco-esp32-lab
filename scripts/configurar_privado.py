"""v0.1.2: formulario local; secretos solo en RAM y NVS autorizada."""

import contextlib
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import queue
import re
import secrets
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import esptool
from esptool.cmds import write_flash, verify_flash
from serial.tools import list_ports
from nvs_partition_gen import NVS, Page

from lab_common import ROOT, read_serial

RESULT = ROOT / "resultados" / "configuracion-v0.1.2.json"
events = queue.Queue()


def result(state, **fields):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(dict(version="0.1.2", state=state, **fields), indent=2), encoding="utf-8"
    )


def build(ssid, password, ap_password, ap_ip):
    target = io.BytesIO()
    salt = secrets.token_bytes(16)
    admin = secrets.token_urlsafe(32)  # Web UI desactivada; no se conserva esta clave.
    hashed = salt.hex() + ":" + hashlib.sha256(salt + admin.encode()).hexdigest()
    with NVS(target, 0x6000 - 0x1000, Page.VERSION2) as nvs:
        nvs.write_namespace("esp32_nat")
        strings = dict(
            ssid=ssid,
            passwd=password,
            ap_ssid="Jocotoco-Lab",
            ap_passwd=ap_password,
            ap_ip=ap_ip,
            web_disabled="1",
            web_password=hashed,
        )
        for key, value in strings.items():
            nvs.write_entry(key, value, "string")
        for key, value in dict(
            ap_authmode=1,
            ap_nat=1,
            ap_disabled=0,
            web_bind=1,
            vpn_enabled=0,
            led_gpio=-1,
            ls_gpio=-1,
            ant_gpio=-1,
            ant_en=-1,
            wd_s=0,
        ).items():
            nvs.write_entry(key, value, "i32")
        for key, value in dict(rc_enabled=0, syslog_en=0, log_level=2).items():
            nvs.write_entry(key, value, "u8")
    data = target.getvalue()
    assert len(data) == 0x6000
    return data


def work(values):
    esp = None
    stage = "preflight"
    try:
        from lab import verify

        with contextlib.redirect_stdout(io.StringIO()):
            verify()
        ports = [p.device for p in list_ports.comports() if p.vid == 0x10C4 and p.pid == 0xEA60]
        if len(ports) != 1:
            raise RuntimeError("port_ambiguous")
        data = build(*values)
        events.put("Guardando configuración por USB… No desconectes la placa.")
        stage = "writing_nvs"
        result(stage)
        # Las salidas de esptool nunca se guardan; no contienen los valores NVS.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            esp = esptool.detect_chip(ports[0])
            if esp.CHIP_NAME != "ESP32":
                raise RuntimeError("wrong_chip")
            esp = esp.run_stub()
            flash_id = esp.flash_id()
            if ((flash_id >> 16) & 255) != 0x16:
                raise RuntimeError("wrong_flash_size")
            write_flash(esp, [(0x9000, data)])
            verify_flash(esp, [(0x9000, data)])
        result("nvs_verified", ssid_ap="Jocotoco-Lab", ap_ip=values[3], web_disabled=True)
        stage = "boot"
        events.put("Configuración verificada. Comprobando arranque y conexión al router…")
        esp.hard_reset()
        port = esp._port
        port.timeout = 0.1
        boot = read_serial(port, 12)
        for _ in range(3):
            port.write(b"\r\n")
            boot += read_serial(port, 2)
            if "esp32>" in boot:
                break
        port.write(b"show status\r\n")
        status = read_serial(port, 5)
        ip = re.search(r"Uplink IP:\s*(\d+\.\d+\.\d+\.\d+)", status)
        connected = bool(ip and ip.group(1) != "0.0.0.0")
        port.write(b"web_ui\r\n")
        web = read_serial(port, 2)
        port.write(b"remote_console status\r\n")
        remote = read_serial(port, 2)
        security_ok = "Web interface: disabled" in web and "disabled" in remote.lower()
        if connected and ipaddress.ip_address(ip.group(1)) in ipaddress.ip_network(
            values[3] + "/24", strict=False
        ):
            raise RuntimeError("subnet_overlap")
        result(
            "configured" if connected and security_ok else "needs_check",
            ssid_ap="Jocotoco-Lab",
            ap_ip=values[3],
            uplink_has_ip=connected,
            web_disabled="Web interface: disabled" in web,
            remote_disabled="disabled" in remote.lower(),
            nvs_verified=True,
            internet_tested=False,
        )
        # No guardar boot, status, SSID doméstico ni credenciales.
        events.put(("done", connected and security_ok))
    except BaseException:
        result("failed", stage=stage, secrets_logged=False)
        events.put(("error", stage))
    finally:
        if esp is not None:
            esp._port.close()


def submit():
    ssid, password, ap_password, confirm = [e.get() for e in entries]
    if not 1 <= len(ssid.encode()) <= 32 or "\x00" in ssid:
        return messagebox.showerror(
            "Revisar", "El nombre de tu Wi-Fi debe tener entre 1 y 32 bytes."
        )
    if not 8 <= len(password) <= 63 or not password.isascii():
        return messagebox.showerror(
            "Revisar", "Ingresa la contraseña WPA2 de tu router (8–63 caracteres ASCII)."
        )
    if not 16 <= len(ap_password) <= 63 or not ap_password.isascii() or ap_password != confirm:
        return messagebox.showerror(
            "Revisar",
            "Usa una contraseña nueva de 16–63 caracteres para Jocotoco-Lab y repítela igual.",
        )
    if ap_password == password:
        return messagebox.showerror(
            "Revisar", "Usa una contraseña distinta a la del router doméstico."
        )
    ap_ip = "192.168.77.1"
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 53))
        if probe.getsockname()[0].startswith("192.168.77."):
            ap_ip = "192.168.78.1"
    except OSError:
        pass
    finally:
        probe.close()
    for entry in entries:
        entry.delete(0, "end")
        entry.configure(state="disabled")
    button.configure(state="disabled")
    threading.Thread(target=work, args=((ssid, password, ap_password, ap_ip),), daemon=True).start()


def poll():
    try:
        while True:
            item = events.get_nowait()
            if isinstance(item, tuple):
                if item[0] == "done":
                    label.set(
                        "Configuración guardada. "
                        + (
                            "Router conectado. Conecta tu teléfono a Jocotoco-Lab para probar internet."
                            if item[1]
                            else "Hace falta comprobar conexión/seguridad; informa a Codex."
                        )
                    )
                else:
                    label.set(
                        "Se detuvo en "
                        + item[1]
                        + ". No desconectes; informa a Codex. No se registraron contraseñas."
                    )
            else:
                label.set(item)
    except queue.Empty:
        pass
    root.after(250, poll)


if __name__ == "__main__":
    result("waiting_private_input")
    root = tk.Tk()
    root.title("Jocotoco-Lab — Configuración privada USB")
    root.geometry("660x440")
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text="Contraseñas solo en esta ventana local y en la placa.", wraplength=600
    ).pack(anchor="w")
    ttk.Label(
        frame, text="Router de 2,4 GHz. La administración web quedará desactivada.", wraplength=600
    ).pack(anchor="w", pady=(0, 12))
    entries = []
    for title, hidden in [
        ("Nombre de tu Wi-Fi doméstico (SSID)", False),
        ("Contraseña de tu Wi-Fi doméstico", True),
        ("Nueva contraseña para Jocotoco-Lab (mínimo 16 caracteres)", True),
        ("Repetir contraseña de Jocotoco-Lab", True),
    ]:
        ttk.Label(frame, text=title).pack(anchor="w")
        entry = ttk.Entry(frame, show="*" if hidden else "", width=70)
        entry.pack(fill="x", pady=(0, 7))
        entries.append(entry)
    button = ttk.Button(frame, text="Guardar configuración autorizada y comprobar", command=submit)
    button.pack(pady=8)
    label = tk.StringVar(
        value="No pegues las contraseñas en el chat. Mantén el micro-USB conectado."
    )
    ttk.Label(frame, textvariable=label, wraplength=600).pack(anchor="w")
    entries[0].focus_set()
    poll()
    root.mainloop()
