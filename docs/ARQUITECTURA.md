# Arquitectura

```text
ESP32 (router + /api/lab/metrics)
    │ HTTP por LAN; opcional USB para diagnóstico
    ▼
dashboard/http_transport.py → dashboard/server.py
                                  │
                         dashboard/storage.py
                                  │
                            SQLite local
                                  │
                        API loopback del monitor
                                  │
                    HTML + history.js + network.js + health.js
```

El muestreo ocurre en un hilo independiente del servidor HTTP. SQLite usa conexiones
cortas, transacciones y WAL. Cada muestra guarda fuente y precisión; los escaneos
tienen inicio/fin y observaciones. Las métricas del dispositivo se registran aparte.
La base queda en `data/`; los datos de ejecución en `resultados/`; nada se versiona.

El componente C añade exclusivamente telemetría de lectura. CPU se calcula como
tiempo no IDLE por núcleo en ventanas de 2 s. RAM es heap interno, no toda SRAM.
Flash distingue aplicación, slot reservado, NVS y volumen de archivos.

`scripts/lab_common.py` contiene detección serial y utilidades sin GUI.
Las ventanas son herramientas explícitas, no servicios secretos en segundo plano.
OTA conserva clave/cookie solo en memoria y restringe las redirecciones al ESP32.

## Límites pendientes

- JavaScript utiliza funciones globales compartidas; no es todavía un frontend modular completo.
- El firmware HTTP básico no expone RSSI por cliente ni BSSID en los escaneos actuales.
- El recolector necesita que la PC esté encendida; no recupera períodos sin conexión.
- Una IP asignada por DHCP puede cambiar; se actualiza en el monitor.
- El esquema usa creación/migraciones aditivas sencillas; no hay motor de migraciones externo.
- Las pruebas son de unidad y almacenamiento; no equivalen a ensayo prolongado de radio/OTA.
