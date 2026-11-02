"""Reconstruye el checkout de firmware fijado sin incluir SDK, secretos ni flash."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(archive_path=None):
    lock = json.loads((ROOT / "firmware/upstream.lock.json").read_text())
    work = ROOT / ".work"
    work.mkdir(exist_ok=True)
    archive = Path(archive_path) if archive_path else work / "upstream.zip"
    if not archive.exists():
        url = "https://codeload.github.com/martin-ger/esp32_nat_router/zip/" + lock["commit"]
        urllib.request.urlretrieve(url, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["source_zip_sha256"]:
        raise RuntimeError("ZIP distinto del origen fijado; no se continúa")
    target = work / "firmware-source"
    if target.exists():
        raise RuntimeError("Ya existe el checkout preparado; no se sobrescribe")
    target.mkdir()
    with zipfile.ZipFile(archive) as z:
        prefix = z.namelist()[0]
        for item in z.infolist():
            relative = item.filename.removeprefix(prefix)
            if not relative or item.is_dir():
                continue
            # Prebuilt images are neither source nor necessary to rebuild.
            if relative.startswith("firmware_"):
                continue
            path = (target / relative).resolve()
            if not path.is_relative_to(target.resolve()):
                raise RuntimeError("Ruta ZIP inválida")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(z.read(item))

    def replace(name, old, new):
        path = target / name
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise RuntimeError("Contexto de integración distinto: " + name)
        path.write_text(text.replace(old, new), encoding="utf-8")

    replace("CMakeLists.txt", 'set(PROJECT_VER "2.4.22")', 'set(PROJECT_VER "2.4.22-joco0.6.0")')
    replace(
        "components/http_server/CMakeLists.txt",
        "app_update esp_app_format mbedtls",
        "app_update esp_app_format mbedtls lab_telemetry",
    )
    replace(
        "components/http_server/http_server.c",
        "/* --- OTA Firmware Upload handler --- */",
        '#include "lab_telemetry.h"\n\n/* --- OTA Firmware Upload handler --- */',
    )
    replace(
        "components/http_server/http_server.c",
        "        httpd_register_uri_handler(server, &ota_uploadp);",
        '        httpd_register_uri_handler(server, &ota_uploadp);\n        esp_err_t lab_err=lab_telemetry_register(server);\n        if (lab_err!=ESP_OK) ESP_LOGW(TAG,"Lab telemetry unavailable: %s",esp_err_to_name(lab_err));',
    )
    shutil.copytree(ROOT / "firmware/components/lab_telemetry", target / "components/lab_telemetry")
    shutil.copy2(ROOT / "firmware/sdkconfig.lab", target / "sdkconfig.lab")
    shutil.copy2(ROOT / "firmware/dependencies.lock", target / "dependencies.lock")
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", help="ZIP oficial ya descargado, opcional")
    prepare(parser.parse_args().source_zip)
