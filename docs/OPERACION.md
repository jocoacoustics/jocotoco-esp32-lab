# Operación y recuperación

## Antes de escribir

Solo ESP32 clásico de 4 MiB, con alimentación estable de 5 V por micro-USB.
Confirmar arquitectura, revisión, imagen, tamaño, hash y particiones compatibles.
Obtener autorización específica inmediatamente antes de cada escritura.
No usar `--force`, quemar eFuses ni borrar toda la flash por defecto.
No pedir conexiones externas a GPIO/VIN/3V3 para este experimento.

## Respaldo inicial

`scripts/lab.py` detecta CP210x, identifica y permite dos lecturas completas de
4 MiB sin sobrescribir archivos. `verify` exige tamaño e igualdad binaria y genera
SHA-256. Los respaldos deben permanecer exclusivamente en `backups/`, excluido de Git.
Pueden contener credenciales. Un respaldo no está incluido en este repositorio.

## OTA privada

`scripts/ota_privado.py` sin argumentos abre únicamente comprobación de acceso.
Necesita la IP configurada desde el monitor y la contraseña administrativa que el
usuario escribe en la ventana. No la guarda en archivos ni argumentos de proceso.
El login va por HTTP al ESP32: es una LAN confiable, no un canal cifrado.

Para instalar, el operador prepara la imagen y presenta versión, tamaño y SHA-256.
Solo tras aprobación se abre con `--image RUTA --authorized-sha256 HASH`.
La contraseña es lo único que introduce el usuario. La herramienta valida cabeceras,
chip, revisión, checksum/digest y slot, pausa consultas, sube, comprueba arranque,
versión/slot y, para el firmware Jocotoco, telemetría. El endpoint valida además
la imagen. No se afirma verificación independiente byte a byte por HTTP.

No cortar alimentación durante la carga. Un fallo de OTA puede dejar la placa sin
conectividad; no se garantiza rollback automático ante todo error. No reutilizar
una autorización de escritura para una imagen distinta.

## Recuperación

Si hay acceso por red, reinstalar una imagen estable revisada mediante OTA con
nueva autorización. Si no lo hay, volver a USB y seguir el procedimiento de lectura,
identificación y programación controlada. Restaurar un respaldo íntegro exige
verificar primero su hash y conservar parámetros de imagen (`keep`). Las imágenes
OTA no sustituyen un respaldo completo de la flash ni cambian una tabla de particiones.

Esta entrega no contiene una restauración ejecutable sin intervención: el operador
debe confirmar imagen, direcciones y permisos. No activar funciones remotas adicionales
ni sensores externos como parte de la recuperación.
