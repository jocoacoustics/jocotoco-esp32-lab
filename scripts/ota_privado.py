"""v0.5.0. Ventana OTA privada. Sin imagen/autorización exacta: solo lectura.

Uso futuro tras autorización en chat: --image APP.bin --authorized-sha256 HASH
No ejecutado en esta entrega: la primera comprobación solo autentica y lee /config.
"""

import argparse
import contextlib
import hashlib
import http.cookiejar
import io
import json
from pathlib import Path
import struct
import sys
import threading
import time
import urllib.request
from urllib.parse import urlencode, urlparse
from esptool.bin_image import ESP32FirmwareImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from http_transport import validate_host, Tables, Client

REPORT = ROOT / "resultados" / "ota-preflight-v0.5.0.json"
worker = None


def inspect_image(path):
    data = Path(path).read_bytes()
    if not 256 < len(data) <= 0x180000:
        raise ValueError("Tamaño incompatible con slot OTA de 1536 KiB")
    with contextlib.redirect_stdout(io.StringIO()):
        image = ESP32FirmwareImage(io.BytesIO(data))
    if (
        image.chip_id != 0
        or image.min_rev_full > 301
        or (image.max_rev_full and image.max_rev_full < 301)
    ):
        raise ValueError("Imagen incompatible con ESP32 clásico revisión 3.1")
    if image.checksum != image.calculate_checksum() or image.calc_digest != image.stored_digest:
        raise ValueError("Checksum o hash interno inválido")
    if struct.unpack_from("<I", data, 32)[0] != 0xABCD5432:
        raise ValueError(
            "Se requiere aplicación OTA con descriptor ESP-IDF; no bootloader ni imagen completa"
        )
    version = data[48:80].split(b"\0")[0].decode("ascii", "replace")
    project = data[80:112].split(b"\0")[0].decode("ascii", "replace")
    return data, dict(
        bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), version=version, project=project
    )


class LocalRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, base):
        self.base = base

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).netloc != urlparse(self.base).netloc or urlparse(newurl).path != "/":
            raise ValueError("Redirección fuera del ESP32 bloqueada")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def save(state, **fields):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(dict(version="0.5.0", state=state, checked_at=time.time(), **fields), indent=2),
        encoding="utf-8",
    )


def operation(password):
    stage = "authentication"
    paused_monitor = False
    local_opener = None
    try:
        link = json.loads(
            (ROOT / "resultados" / "acceso-red-v0.4.0.json").read_text(encoding="utf-8")
        )
        base = "http://" + validate_host(link["host"])
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(jar),
            LocalRedirect(base),
        )
        login = urllib.request.Request(
            base + "/",
            data=urlencode({"login_password": password}).encode(),
            headers={"Origin": base, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with opener.open(login, timeout=15) as response:
            response.read(400000)
        with opener.open(base + "/config", timeout=15) as response:
            html = response.read(500000).decode("utf-8", "replace")
        table = Tables()
        table.feed(html)
        rows = {r[0].rstrip(":"): r[1] for r in table.rows if len(r) == 2}
        if rows.get("Chip") != "ESP32" or not rows.get("Running") or "/api/ota-upload" not in html:
            raise ValueError("No se confirmó autenticación y capacidad OTA")
        live = {k: rows[k] for k in ("Chip", "Running", "Version", "Built") if k in rows}
        save("preflight_ok", flash_written=False, device=live)
        if not args.image:
            root.after(
                0,
                lambda: status.set(
                    "Acceso OTA verificado. No se escribió flash. Puedes cerrar esta ventana."
                ),
            )
            return
        stage = "image_validation"
        data, info = inspect_image(args.image)
        if not args.authorized_sha256:
            save("image_checked_not_written", flash_written=False, device=live, image=info)
            root.after(
                0,
                lambda: status.set(
                    "Imagen y acceso comprobados. Falta autorización específica; no se escribió flash."
                ),
            )
            return
        if args.authorized_sha256.lower() != info["sha256"]:
            raise ValueError("Hash distinto de la imagen autorizada")
        # Pause optional PC polling during the authorized write; preserve user pause.
        try:
            local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with local_opener.open("http://127.0.0.1:8785/api/state", timeout=3) as response:
                monitor = json.loads(response.read(100000))
            if not monitor.get("paused"):
                pause = urllib.request.Request(
                    "http://127.0.0.1:8785/api/pause",
                    data=b"",
                    headers={"Origin": "http://127.0.0.1:8785"},
                    method="POST",
                )
                with local_opener.open(pause, timeout=3) as response:
                    response.read(1000)
                paused_monitor = True
                time.sleep(4)
        except Exception:
            pass
        stage = "ota_upload"
        save("uploading", flash_written="in_progress", device=live, image=info)
        req = urllib.request.Request(
            base + "/api/ota-upload",
            data=data,
            headers={"Origin": base, "Content-Type": "application/octet-stream"},
            method="POST",
        )
        with opener.open(req, timeout=180) as response:
            result = json.loads(response.read(8192))
        if result.get("ok") is not True:
            raise ValueError("OTA rechazada")
        stage = "post_boot_verification"
        save("accepted_awaiting_boot", flash_written=True, image=info)
        time.sleep(8)
        confirmed = False
        version_verified = False
        telemetry_verified = False
        for _ in range(8):
            try:
                Client(link["host"]).poll()
                confirmed = True
                req = urllib.request.Request(
                    base + "/",
                    data=urlencode({"login_password": password}).encode(),
                    headers={"Origin": base, "Content-Type": "application/x-www-form-urlencoded"},
                )
                with opener.open(req, timeout=15) as response:
                    response.read(400000)
                with opener.open(base + "/config", timeout=15) as response:
                    new_html = response.read(500000).decode("utf-8", "replace")
                table = Tables()
                table.feed(new_html)
                current = {r[0].rstrip(":"): r[1] for r in table.rows if len(r) == 2}
                version_verified = current.get("Version") == info["version"] and current.get(
                    "Running"
                ) != live.get("Running")
                if version_verified and "joco0.6." in info["version"]:
                    metrics = Client(link["host"]).metrics()
                    telemetry_verified = metrics.get("firmware_version") == info[
                        "version"
                    ] and metrics["cpu"].get("valid", False)
                    if not telemetry_verified:
                        time.sleep(2)
                        continue
                if version_verified:
                    break
            except Exception:
                time.sleep(3)
        verified = version_verified and ("joco0.6." not in info["version"] or telemetry_verified)
        save(
            "updated_verified" if verified else "accepted_boot_unverified",
            flash_written=True,
            image=info,
            runtime_version_verified=version_verified,
            telemetry_verified=telemetry_verified,
        )
        root.after(
            0,
            lambda: status.set(
                "Actualización verificada: versión, partición y telemetría esperadas."
                if verified
                else "Carga aceptada; falta confirmar arranque/telemetría. Informa a Codex."
            ),
        )
    except BaseException:
        save("failed", stage=stage, flash_written=stage in ("ota_upload", "post_boot_verification"))
        root.after(
            0,
            lambda: status.set(
                "Comprobación detenida en "
                + stage
                + ". No se registró la contraseña. Informa a Codex."
            ),
        )
    finally:
        if paused_monitor and local_opener:
            try:
                resume = urllib.request.Request(
                    "http://127.0.0.1:8785/api/pause",
                    data=b"",
                    headers={"Origin": "http://127.0.0.1:8785"},
                    method="POST",
                )
                with local_opener.open(resume, timeout=3) as response:
                    response.read(1000)
            except Exception:
                pass
        password = None
        root.after(0, lambda: button.configure(text="Finalizado. Puedes cerrar la ventana."))


def submit():
    global worker
    password = entry.get()
    if not password:
        return
    entry.delete(0, "end")
    entry.configure(state="disabled")
    button.configure(state="disabled")
    status.set(
        "Comprobando acceso…"
        if not args.authorized_sha256
        else "Actualizando únicamente la imagen autorizada… No cortes la alimentación."
    )
    worker = threading.Thread(target=operation, args=(password,), daemon=False)
    worker.start()


def close():
    if worker is not None and worker.is_alive():
        messagebox.showinfo(
            "Operación en curso",
            "Espera a que termine la comprobación o actualización antes de cerrar.",
        )
    else:
        root.destroy()


if __name__ == "__main__":
    import tkinter as tk
    from tkinter import ttk, messagebox

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image")
    parser.add_argument("--authorized-sha256")
    args = parser.parse_args()
    if args.authorized_sha256 and not args.image:
        parser.error("Falta imagen revisada")
    info = inspect_image(args.image)[1] if args.image else None
    save("waiting_private_input", flash_written=False, image=info)
    root = tk.Tk()
    root.title("Jocotoco — Actualización OTA privada")
    root.geometry("660x330")
    root.protocol("WM_DELETE_WINDOW", close)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text="Introduce solo tu contraseña administrativa del ESP32.", wraplength=610
    ).pack(anchor="w")
    summary = (
        ("Imagen: " + info["project"] + " " + info["version"] + "\nSHA-256: " + info["sha256"])
        if info
        else "Modo actual: comprobar acceso OTA; no hay firmware pendiente y no se escribe flash."
    )
    ttk.Label(frame, text=summary, wraplength=610).pack(anchor="w", pady=12)
    ttk.Label(
        frame,
        text="Se envía por HTTP a la IP local configurada. No se guarda en archivos ni logs.",
        wraplength=610,
    ).pack(anchor="w")
    entry = ttk.Entry(frame, show="*", width=65)
    entry.pack(fill="x", pady=12)
    button = ttk.Button(
        frame,
        text=(
            "Instalar imagen específicamente autorizada"
            if args.authorized_sha256
            else "Comprobar acceso sin escribir flash"
        ),
        command=submit,
    )
    button.pack(pady=5)
    status = tk.StringVar(
        value="USB no necesario. Mantén el ESP32 alimentado y conectado al router."
    )
    ttk.Label(frame, textvariable=status, wraplength=610).pack(anchor="w", pady=10)
    entry.focus_set()
    root.mainloop()
