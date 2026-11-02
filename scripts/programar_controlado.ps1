# v0.1.1. Obtener autorización específica en el chat antes de cada escritura.
param(
    [Parameter(Mandatory=$true)][ValidateSet('instalar','restaurar')][string]$Operacion,
    [Parameter(Mandatory=$true)][string]$Autorizacion
)
$ErrorActionPreference='Stop'
if($Autorizacion -cne "AUTORIZO $Operacion FLASH") { throw 'Falta autorización explícita' }
$taskRoot=Split-Path $PSScriptRoot -Parent
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
if(-not (Test-Path -LiteralPath $taskPython)){$taskPython=(Get-Command python -ErrorAction Stop).Source}
& $taskPython "$PSScriptRoot/lab.py" verify
if($LASTEXITCODE -ne 0){throw 'Respaldo inválido'}
$taskPort=(& $taskPython "$PSScriptRoot/lab.py" detect).Trim()
if($LASTEXITCODE -ne 0){throw 'Puerto ambiguo'}
# Confirmar chip y protecciones por lectura antes de iniciar cualquier escritura.
& $taskPython -m esptool --chip esp32 --port $taskPort --after no-reset flash-id
if($LASTEXITCODE -ne 0){throw 'Identificación fallida'}
& $taskPython -m espefuse --chip esp32 --port $taskPort summary
if($LASTEXITCODE -ne 0){throw 'No se pudieron comprobar protecciones'}
if((Read-Host 'Confirma ESP32 clásico, flash 4MB y ausencia de cifrado/secure boot; escribe COMPATIBLE') -cne 'COMPATIBLE'){throw 'Cancelado'}
if($Operacion -eq 'instalar'){
    $taskManifest=Get-Content "$taskRoot/resultados/firmware.json" -Raw | ConvertFrom-Json
    foreach($taskEntry in $taskManifest.sha256.PSObject.Properties){
        if((Get-FileHash "$taskRoot/firmware/$($taskEntry.Name)" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.Value){throw 'Firmware alterado'}
    }
    & $taskPython "$PSScriptRoot/lab.py" firmware
    if($LASTEXITCODE -ne 0){throw 'Firmware incompatible'}
    $taskParts=@('0x1000',"$taskRoot/firmware/bootloader.bin",'0x8000',"$taskRoot/firmware/partition-table.bin",'0xf000',"$taskRoot/firmware/ota_data_initial.bin",'0x20000',"$taskRoot/firmware/esp32_nat_router.bin")
    $taskOptions=@('--flash-mode','dio','--flash-freq','40m','--flash-size','4MB')
}else{
    $taskParts=@('0x0',"$taskRoot/backups/original_lectura_1.bin")
    $taskOptions=@('--flash-mode','keep','--flash-freq','keep','--flash-size','keep')
}
if((Read-Host "Último control: escribe ESCRIBIR para $Operacion") -cne 'ESCRIBIR'){throw 'Cancelado'}
& $taskPython -m esptool --chip esp32 --port $taskPort --baud 115200 --after no-reset write-flash @taskOptions @taskParts
if($LASTEXITCODE -ne 0){throw 'Escritura fallida: detener y diagnosticar'}
& $taskPython -m esptool --chip esp32 --port $taskPort --after no-reset verify-flash @taskOptions @taskParts
if($LASTEXITCODE -ne 0){throw 'Verificación fallida: no arrancar'}
Write-Output 'Flash verificada. Se mantiene en bootloader; configurar arranque seguro antes de reiniciar.'
