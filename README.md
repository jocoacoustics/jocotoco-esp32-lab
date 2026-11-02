# Jocotoco ESP32 Lab

Laboratorio local de Wi-Fi para ESP32 clásico: router NAT AP+STA, observación de
redes 2,4 GHz, historial SQLite y telemetría real de CPU, heap y aplicación en flash.

**Entrega de fuentes v0.6.1. Firmware integrado: 2.4.22-joco0.6.0.**
No incluye credenciales, respaldos de dispositivos, bases de datos, redes observadas,
SDK, entornos Python ni binarios. No requiere servicios de nube.

## Estructura

| Carpeta                              | Responsabilidad                                              |
| ------------------------------------ | ------------------------------------------------------------ |
| `dashboard/`                         | Servidor local, transporte HTTP/USB, SQLite e interfaz       |
| `scripts/`                           | Configuración privada, comprobaciones y OTA con autorización |
| `firmware/components/lab_telemetry/` | Código C propio de métricas                                  |
| `firmware/upstream.lock.json`        | Repositorio y revisión exactos del router base               |
| `firmware/dependencies.lock`         | Dependencias de compilación fijadas                          |
| `tests/`                             | Pruebas independientes de hardware y datos privados          |
| `docs/`                              | Arquitectura, operación y procedencia                        |

## Instalar y ejecutar el monitor

Python 3.12, conexión a la misma red local que el ESP32. Tkinter es necesario para
las ventanas privadas; suele venir con Python para Windows. El servidor no usa Tk.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe dashboard\server.py
```

Abre `http://127.0.0.1:8785`. En **Conexión inalámbrica**, ingresa la IP privada
del ESP32. No se incluye la IP de ningún dispositivo real en la configuración.
En Windows también puedes ejecutar `dashboard/Iniciar_panel.ps1`.

El ESP32 puede alimentarse solo con un cargador micro-USB de 5 V. La PC debe seguir
encendida para registrar. Los datos se guardan en `data/jocotoco_wifi.sqlite3`.
Cerrar la pestaña no detiene el servidor. No se instala inicio automático.
Para USB, conectar un único CP210x; `JOCOTOCO_PORT` permite indicar otro puerto.

## Qué mide

- RSSI del enlace, clientes y contadores de tráfico publicados por el router.
- Redes visibles por escaneo; intervalo configurable, 60 s predeterminados.
- CPU global/por núcleo y heap libre/usado si el firmware de telemetría está instalado.
- Imagen activa y porcentaje de slot OTA, NVS por entradas y volumen de archivos.
- Series temporales en SQLite y exportación JSON; reloj del PC mostrado en Ecuador.

HTTP del firmware base redondea contadores de tráfico: las tasas son aproximadas.
La agrupación de redes usa SSID + canal + seguridad; no identifica antenas únicas
sin BSSID. Ausencia de observación no se convierte en 0 dBm. RSSI no demuestra
movimiento, posición ni distancia. BLE/CSI, voltaje y temperatura no se implementan.

## Pruebas

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
node --check dashboard/main.js
node --check dashboard/history.js
node --check dashboard/network.js
node --check dashboard/health.js
```

Las pruebas usan datos ficticios y SQLite temporal. No acceden a una placa ni
dependen de archivos locales de credenciales o de un firmware descargado.
GitHub Actions incluye el mismo chequeo; no se ha ejecutado remotamente aún.

## Reconstruir firmware

Requiere el entorno oficial **ESP-IDF 5.5.4** ya instalado y activado. En Windows,
mantener el SDK/toolchain en una ruta sin espacios evita fallos del driver Xtensa.

```powershell
.venv\Scripts\python.exe scripts/preparar_firmware.py
# En una terminal con el entorno oficial ESP-IDF exportado:
./scripts/compilar_telemetria.ps1
```

El preparador verifica el ZIP del commit fijado, copia el componente C e integra
los cambios controlados. Todo lo generado queda en `.work/`, excluido de Git.
También acepta `--source-zip` para reutilizar el ZIP oficial sin descargarlo.
El script de compilación no escribe flash. El hash del binario validado durante
el experimento original consta en `firmware/release-v0.6.0.json`; las marcas de
compilación pueden producir un hash distinto al reconstruirlo.

## OTA y seguridad

Consulta [operación](docs/OPERACION.md) antes de usar las herramientas de escritura.
La ventana OTA pide la contraseña administrativa solo localmente. Sin imagen y
hash específicamente autorizados, solo comprueba acceso: no escribe flash.
Ninguna herramienta debe usarse para actualizar o restaurar sin consentimiento
inmediatamente previo. USB permanece como vía de recuperación.

HTTP no cifra tráfico. La contraseña protege la administración; el firmware base
publica parte del estado y los escaneos sin login. Usar solo en una LAN confiable,
sin reenvío de puertos a internet. El servidor del PC escucha solo en loopback.

## Estado del código

Esta entrega ordena fuentes y configuración y elimina dependencias de una PC
particular. La interfaz sigue usando JavaScript compartido entre módulos; una
refactorización futura puede convertirlo en módulos ES y separar estilos/plantillas.
No se afirma cobertura completa, endurecimiento de producción ni detección de movimiento.
Las fuentes de terceros conservan su procedencia y avisos: ver [NOTICE](NOTICE.md).

## Git local

La entrega se prepara como repositorio independiente. No tiene remoto ni se sube
automáticamente. Puedes añadir después tu repositorio destino; no uses la carpeta
operativa del experimento como sustituto de esta entrega limpia.
