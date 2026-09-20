[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'scripts/runtime-common.ps1')
$directorMutex = Enter-DirectorLock
try {
    Stop-DirectorProcess 'web'
    Stop-DirectorProcess 'backend'
    Write-Host 'Done. Only verified services recorded by this project were considered.'
} finally {
    $directorMutex.ReleaseMutex()
    $directorMutex.Dispose()
}
