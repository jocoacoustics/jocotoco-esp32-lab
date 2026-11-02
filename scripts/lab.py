"""Jocotoco ESP32 Lab v0.1.0: operaciones de lectura; nunca escribe flash."""

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def partitions(data):
    rows = []
    for pos in range(0, len(data), 32):
        row = data[pos : pos + 32]
        if len(row) != 32 or row[:2] != b"\xaa\x50":
            break
        _, typ, sub, offset, size, label, flags = struct.unpack("<HBBII16sI", row)
        rows.append(
            dict(
                type=typ,
                subtype=sub,
                offset=offset,
                size=size,
                label=label.split(b"\0")[0].decode("ascii", "replace"),
                flags=flags,
            )
        )
    return rows


def verify():
    paths = [ROOT / "backups" / f"original_lectura_{n}.bin" for n in (1, 2)]
    blobs = [p.read_bytes() for p in paths]
    if any(len(b) != 0x400000 for b in blobs) or blobs[0] != blobs[1]:
        raise SystemExit("ALTO: respaldos incompletos o diferentes")
    result = {
        "version": "0.1.0",
        "bytes": len(blobs[0]),
        "binary_equal": True,
        "files": {p.name: digest(b) for p, b in zip(paths, blobs)},
        "partitions_at_0x8000": partitions(blobs[0][0x8000:0x9000]),
    }
    manifest = ROOT / "resultados" / "integridad.json"
    if (
        manifest.exists()
        and json.loads(manifest.read_text(encoding="utf-8"))["files"] != result["files"]
    ):
        raise SystemExit("ALTO: hashes distintos del manifiesto original")
    (ROOT / "resultados").mkdir(parents=True, exist_ok=True)
    (ROOT / "resultados" / "integridad.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    # No leer ni imprimir valores de NVS: pueden contener secretos.
    print(json.dumps(result, indent=2))


def firmware():
    base = ROOT / "firmware"
    rows = partitions((base / "partition-table.bin").read_bytes())
    assert rows and max(r["offset"] + r["size"] for r in rows) <= 0x400000
    app = (base / "esp32_nat_router.bin").read_bytes()
    ota = next(r for r in rows if r["type"] == 0 and r["subtype"] == 16)
    assert ota["offset"] == 0x20000 and len(app) <= ota["size"]
    for name in ("bootloader.bin", "esp32_nat_router.bin"):
        data = (base / name).read_bytes()
        assert data[0] == 0xE9 and int.from_bytes(data[12:14], "little") == 0
        subprocess.run(
            [sys.executable, "-m", "esptool", "image-info", str(base / name)], check=True
        )
    result = {
        "partitions": rows,
        "fits_4MB": True,
        "sha256": {p.name: digest(p.read_bytes()) for p in base.glob("*.bin")},
    }
    (ROOT / "resultados").mkdir(parents=True, exist_ok=True)
    (ROOT / "resultados" / "firmware.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["detect", "identify", "backup", "verify", "firmware"])
    parser.add_argument("--reading", type=int, choices=[1, 2])
    args = parser.parse_args()
    if args.action == "verify":
        return verify()
    if args.action == "firmware":
        return firmware()
    ports = [p for p in list_ports.comports() if p.vid == 0x10C4 and p.pid == 0xEA60]
    if len(ports) != 1:
        raise SystemExit("ALTO: se requiere exactamente un CP210x conectado")
    port = ports[0].device
    if args.action == "detect":
        print(port)
        return
    cmd = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp32",
        "--port",
        port,
        "--baud",
        "115200",
        "--after",
        "no-reset",
    ]
    if args.action == "identify":
        cmd += ["flash-id"]
    else:
        if not args.reading:
            parser.error("--reading requerido")
        output = ROOT / "backups" / f"original_lectura_{args.reading}.bin"
        if output.exists():
            raise SystemExit("ALTO: no se sobrescribe un respaldo existente")
        cmd += ["read-flash", "0x0", "0x400000", str(output), "--no-progress"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
