# Solo compila; nunca escribe en una placa. Ejecutar después de export.ps1 de ESP-IDF.
param([string]$IdfPath=$env:IDF_PATH,[string]$Python='python')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
if(-not $IdfPath -or -not (Test-Path (Join-Path $IdfPath 'tools/idf.py'))){throw 'Activa el entorno oficial ESP-IDF 5.5.4 o indica -IdfPath'}
$taskSource=Join-Path $taskRoot '.work/firmware-source'
if(-not (Test-Path (Join-Path $taskSource 'CMakeLists.txt'))){throw 'Ejecuta primero scripts/preparar_firmware.py'}
$env:IDF_TARGET='esp32'
& $Python (Join-Path $IdfPath 'tools/idf.py') -C $taskSource -B (Join-Path $taskRoot '.work/build') -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.lab' build
if($LASTEXITCODE -ne 0){throw 'Compilación fallida; no se ha escrito flash'}
