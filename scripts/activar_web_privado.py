"""v0.2.1. Activación web autorizada; modifica solo dos valores NVS existentes."""

import contextlib
import hashlib
import io
import json
import secrets
import struct
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import zlib
import esptool
from esptool.cmds import read_flash, write_flash, verify_flash
from lab_common import ROOT, read_serial, detect_port

RESULT = ROOT / "resultados" / "acceso-wifi-v0.2.1.json"


def result(state, **fields):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(dict(version="0.2.1", state=state, **fields), indent=2), encoding="utf-8"
    )


def entries(data):
    pages = []
    for base in range(0, len(data), 4096):
        page = data[base : base + 4096]
        if struct.unpack_from("<I", page)[0] in (0xFFFFFFFE, 0xFFFFFFFC):
            pages.append((struct.unpack_from("<I", page, 4)[0], base))
    for _, base in sorted(pages):
        index = 0
        while index < 126:
            pos = base + 64 + index * 32
            row = data[pos : pos + 32]
            state = (data[base + 32 + index // 4] >> ((index % 4) * 2)) & 3
            if state != 2:
                index += 1
                continue
            span = row[2]
            if not 1 <= span <= 126 - index:
                raise ValueError("span")
            crc = zlib.crc32(row[:4] + row[8:], 0xFFFFFFFF) & 0xFFFFFFFF
            if crc != struct.unpack_from("<I", row, 4)[0]:
                raise ValueError("crc")
            key = row[8:24].split(b"\0")[0].decode("ascii")
            yield pos, row, key
            index += span


def patch(data, password):
    original = bytes(data)
    data = bytearray(data)
    records = list(entries(data))
    ns = [row[24] for _, row, key in records if row[0] == 0 and key == "esp32_nat"]
    if len(set(ns)) != 1:
        raise ValueError("namespace")
    namespace = ns[0]
    latest = {key: (pos, row) for pos, row, key in records if row[0] == namespace}

    def value(key):
        pos, row = latest[key]
        if row[1] != 0x21:
            raise ValueError("string")
        length = struct.unpack_from("<H", row, 24)[0]
        payload = bytes(data[pos + 32 : pos + 32 + length])
        if zlib.crc32(payload, 0xFFFFFFFF) & 0xFFFFFFFF != struct.unpack_from("<I", row, 28)[0]:
            raise ValueError("payload_crc")
        return payload

    # Verifica que las restricciones ya existentes siguen presentes.
    for key in ("web_bind", "rc_enabled"):
        row = latest[key][1]
        expected = 1 if key == "web_bind" else 0
        size = 4 if key == "web_bind" else 1
        if int.from_bytes(row[24 : 24 + size], "little") != expected:
            raise ValueError("unsafe_binding")
    before = {key: value(key) for key in ("ssid", "passwd", "ap_ssid", "ap_passwd", "ap_ip")}
    salt = secrets.token_bytes(16)
    hashed = salt.hex() + ":" + hashlib.sha256(salt + password.encode()).hexdigest()
    allowed = set()
    for key, new in [("web_password", hashed), ("web_disabled", "0")]:
        pos, row = latest[key]
        old = value(key)
        payload = new.encode() + b"\0"
        if len(payload) != len(old):
            raise ValueError("length_changed")
        data[pos + 32 : pos + 32 + len(payload)] = payload
        struct.pack_into("<I", data, pos + 28, zlib.crc32(payload, 0xFFFFFFFF) & 0xFFFFFFFF)
        row = data[pos : pos + 32]
        struct.pack_into(
            "<I", data, pos + 4, zlib.crc32(row[:4] + row[8:], 0xFFFFFFFF) & 0xFFFFFFFF
        )
        allowed.update(range(pos, pos + 32 + len(payload)))
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(original, data))):
        raise ValueError("unexpected_change")
    if before != {key: value(key) for key in before}:
        raise ValueError("credentials_changed")
    list(entries(data))  # Revalida CRC de todas las entradas.
    return bytes(data)


def work(password):
    esp = None
    stage = "reading_nvs"
    try:
        result(stage)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            esp = esptool.detect_chip(detect_port())
            if esp.CHIP_NAME != "ESP32":
                raise ValueError("chip")
            esp = esp.run_stub()
            original = read_flash(esp, 0x9000, 0x6000, no_progress=True)
            data = patch(original, password)
            stage = "writing_nvs"
            result(stage)
            write_flash(esp, [(0x9000, data)])
            verify_flash(esp, [(0x9000, data)])
        stage = "checking_boot"
        result(stage, nvs_verified=True)
        esp.hard_reset()
        port = esp._port
        port.timeout = 0.1
        read_serial(port, 12)
        port.write(b"\r\n")
        read_serial(port, 2)
        port.write(b"web_ui\r\n")
        web = read_serial(port, 3)
        port.write(b"remote_console status\r\n")
        remote = read_serial(port, 3)
        ok = "Web interface: enabled" in web and "bind: AP " in web and "disabled" in remote.lower()
        result(
            "enabled" if ok else "needs_check",
            nvs_verified=True,
            credentials_preserved=True,
            web_ap_only="bind: AP " in web,
            remote_disabled="disabled" in remote.lower(),
            url="http://192.168.77.1",
            password_set=True,
        )
        root.after(
            0,
            lambda: status.set(
                "Acceso activado y verificado. Conéctate a Jocotoco-Lab y abre http://192.168.77.1"
                if ok
                else "Configuración guardada; Codex debe comprobar el estado."
            ),
        )
    except BaseException:
        result("failed", stage=stage)
        root.after(
            0,
            lambda: status.set(
                "Se detuvo en " + stage + ". Mantén USB conectado e informa a Codex."
            ),
        )
    finally:
        if esp:
            esp._port.close()


def submit():
    password, confirm = first.get(), second.get()
    if password != confirm or not 16 <= len(password) <= 63 or not password.isascii():
        return messagebox.showerror(
            "Revisar", "Usa una contraseña nueva de 16–63 caracteres ASCII y repítela igual."
        )
    for entry in (first, second):
        entry.delete(0, "end")
        entry.configure(state="disabled")
    button.configure(state="disabled")
    status.set("Guardando la configuración autorizada. No desconectes el USB…")
    threading.Thread(target=work, args=(password,), daemon=True).start()


if __name__ == "__main__":
    result("waiting_private_input")
    root = tk.Tk()
    root.title("Jocotoco-Lab — Acceso Wi-Fi protegido")
    root.geometry("630x340")
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text="Activa administración únicamente desde Jocotoco-Lab.", wraplength=570
    ).pack(anchor="w")
    ttk.Label(
        frame,
        text="HTTP sin cifrado. Conserva las contraseñas Wi-Fi existentes.\nLa consola TCP seguirá apagada.",
        wraplength=570,
    ).pack(anchor="w", pady=10)
    ttk.Label(frame, text="Nueva contraseña de administración (mínimo 16 caracteres)").pack(
        anchor="w"
    )
    first = ttk.Entry(frame, show="*", width=65)
    first.pack(fill="x", pady=5)
    ttk.Label(frame, text="Repetir contraseña de administración").pack(anchor="w")
    second = ttk.Entry(frame, show="*", width=65)
    second.pack(fill="x", pady=5)
    button = ttk.Button(frame, text="Activar acceso Wi-Fi autorizado", command=submit)
    button.pack(pady=10)
    status = tk.StringVar(
        value="No ingreses aquí la clave del router; crea una clave administrativa nueva."
    )
    ttk.Label(frame, textvariable=status, wraplength=570).pack(anchor="w")
    first.focus_set()
    root.mainloop()
