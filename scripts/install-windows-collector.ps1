#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$expectedVersion = '0.61.0'
$repository = Split-Path -Parent $PSScriptRoot
$sourceConfig = Join-Path $repository 'infrastructure\vector-windows\vector.yaml'
$vectorRoot = 'C:\Program Files\Vector'
$vectorExe = Join-Path $vectorRoot 'bin\vector.exe'
$configDirectory = Join-Path $vectorRoot 'config'
$targetConfig = Join-Path $configDirectory 'vector.yaml'
$vendorBackup = Join-Path $configDirectory 'vector.yaml.vendor-default'
$dataDirectory = 'C:\ProgramData\OpenSecurityLakehouse\vector-data'
$sourceCertificates = Join-Path $repository 'data\mtls\clients\windows'
$certificateDirectory = 'C:\ProgramData\OpenSecurityLakehouse\mtls'
$taskName = 'OpenSecurityLakehouseVector'
$localServiceSid = 'S-1-5-19'
$eventLogReadersSid = 'S-1-5-32-573'

if (-not (Test-Path -LiteralPath $vectorExe)) {
    throw "Vector is not installed at $vectorExe"
}
if (-not (Test-Path -LiteralPath $sourceConfig)) {
    throw "Collector configuration was not found at $sourceConfig"
}
foreach ($certificate in @('ca.crt', 'client.crt', 'client.key')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceCertificates $certificate))) {
        throw "Missing mTLS certificate: $certificate"
    }
}

$installedVersion = (& $vectorExe --version | Select-Object -First 1)
if ($installedVersion -notmatch "^vector $([regex]::Escape($expectedVersion))\b") {
    throw "Expected Vector $expectedVersion, found: $installedVersion"
}

New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $certificateDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceCertificates 'ca.crt') -Destination $certificateDirectory -Force
Copy-Item -LiteralPath (Join-Path $sourceCertificates 'client.crt') -Destination $certificateDirectory -Force
Copy-Item -LiteralPath (Join-Path $sourceCertificates 'client.key') -Destination $certificateDirectory -Force
& icacls.exe $certificateDirectory /inheritance:r /grant:r `
    '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-32-544:(OI)(CI)F' `
    "*$localServiceSid`:(OI)(CI)R" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to restrict the mTLS certificate directory ACL.'
}
& icacls.exe $dataDirectory /inheritance:r /grant:r `
    '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-32-544:(OI)(CI)F' `
    "*$localServiceSid`:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to restrict the Vector data directory ACL.'
}

$eventLogReaders = Get-LocalGroup -SID $eventLogReadersSid
$alreadyMember = Get-LocalGroupMember -SID $eventLogReaders.SID -ErrorAction SilentlyContinue |
    Where-Object { $_.SID -eq $localServiceSid }
if (-not $alreadyMember) {
    Add-LocalGroupMember -SID $eventLogReaders.SID -Member $localServiceSid
}

if ((Test-Path -LiteralPath $targetConfig) -and -not (Test-Path -LiteralPath $vendorBackup)) {
    Copy-Item -LiteralPath $targetConfig -Destination $vendorBackup
}
Copy-Item -LiteralPath $sourceConfig -Destination $targetConfig -Force

& $vectorExe validate $targetConfig
if ($LASTEXITCODE -ne 0) {
    throw 'Vector rejected the OSL Windows collector configuration.'
}

$action = New-ScheduledTaskAction -Execute $vectorExe -Argument "--config `"$targetConfig`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
    -UserId $localServiceSid `
    -LogonType ServiceAccount `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Collect Windows Event Log for Open Security Lakehouse' `
    -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Output "OSL Windows collector installed as task $taskName."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
