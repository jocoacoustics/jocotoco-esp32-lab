# Validación de la entrega local v0.6.1

- Se separó de la carpeta operativa; no se modificó el servicio activo para empaquetar.
- Se eliminaron las rutas de usuario/Conda y el COM fijo en las herramientas exportadas.
- Las utilidades de serial se separaron de la GUI.
- Las pruebas dejaron de depender de configuración privada y binarios externos.
- Se incluyó el componente C directamente, una receta de integración y dependencias fijadas.
- El checkout reconstruido desde el ZIP oficial coincide con las fuentes del firmware instalado.
- Nueve pruebas de unidad, SQLite y servicio HTTP local pasan en la copia independiente.
- Python y JavaScript se verifican sintácticamente; se separaron estilos y lógica del HTML y se formateó el código para lectura.
- Los directorios operativos, SDK, compilaciones y respaldos quedan fuera de Git.
- No se incluye ni se ejecuta un despliegue automático en CI.
- No se configuró remoto ni se publicó nada.

La estructura es adecuada para una primera entrega versionada. Sigue siendo un
laboratorio, no un sistema con cobertura completa o frontend totalmente refactorizado.
El estado remoto de GitHub Actions no se afirma: aún no se ha subido el repositorio.
